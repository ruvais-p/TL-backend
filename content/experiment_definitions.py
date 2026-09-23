import math
import re


SUPPORTED_RENDERERS = frozenset({"geogebra", "placeholder", "graphspace"})
SUPPORTED_COMPLETION_OPERATORS = frozenset(
    {
        "equals",
        "not_equals",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "truthy",
    }
)
MULTIVARIABLE_STEP_KINDS = ("hill", "slope", "walk", "result", "question")
SLOPE_DIRECTIONS = frozenset({"increase", "decrease", "same"})


class ExperimentDefinitionError(ValueError):
    pass


def _non_empty_string(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ExperimentDefinitionError(f"{path} must be a non-empty string.")


def _number(value, path):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ExperimentDefinitionError(f"{path} must be a finite number.")


def _workspace_id(value, path):
    _non_empty_string(value, path)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise ExperimentDefinitionError(
            f"{path} must start with a letter and contain only letters, numbers, or underscores."
        )


def _validate_linear_programming_workspace(workspace):
    if not isinstance(workspace, dict):
        raise ExperimentDefinitionError("renderer_config.workspace must be an object.")
    if workspace.get("type") != "linear_programming":
        raise ExperimentDefinitionError("renderer_config.workspace.type must be linear_programming.")

    variables = workspace.get("variables")
    if not isinstance(variables, list) or not 2 <= len(variables) <= 12:
        raise ExperimentDefinitionError("renderer_config.workspace.variables must contain 2 to 12 variables.")
    variable_ids = []
    for index, variable in enumerate(variables):
        path = f"renderer_config.workspace.variables[{index}]"
        if not isinstance(variable, dict):
            raise ExperimentDefinitionError(f"{path} must be an object.")
        variable_id = variable.get("id")
        _workspace_id(variable_id, f"{path}.id")
        variable_ids.append(variable_id)
        for field in ("min", "max", "initial"):
            _number(variable.get(field), f"{path}.{field}")
        if variable["min"] >= variable["max"]:
            raise ExperimentDefinitionError(f"{path}.min must be smaller than {path}.max.")
        if not variable["min"] <= variable["initial"] <= variable["max"]:
            raise ExperimentDefinitionError(f"{path}.initial must be between min and max.")
        if "step" in variable:
            _number(variable["step"], f"{path}.step")
            if variable["step"] <= 0:
                raise ExperimentDefinitionError(f"{path}.step must be positive.")
        for field in ("label", "symbol", "unit"):
            if field in variable:
                _non_empty_string(variable[field], f"{path}.{field}")
    if len(set(variable_ids)) != len(variable_ids):
        raise ExperimentDefinitionError("renderer_config.workspace variable IDs must be unique.")

    axes = workspace.get("axis_variables")
    if (
        not isinstance(axes, list)
        or len(axes) != 2
        or axes[0] == axes[1]
        or any(axis not in variable_ids for axis in axes)
    ):
        raise ExperimentDefinitionError(
            "renderer_config.workspace.axis_variables must contain two different variable IDs."
        )

    objective = workspace.get("objective")
    if not isinstance(objective, dict):
        raise ExperimentDefinitionError("renderer_config.workspace.objective must be an object.")
    if objective.get("sense") not in {"maximize", "minimize"}:
        raise ExperimentDefinitionError(
            "renderer_config.workspace.objective.sense must be maximize or minimize."
        )
    coefficients = objective.get("coefficients")
    if not isinstance(coefficients, dict) or set(coefficients) != set(variable_ids):
        raise ExperimentDefinitionError(
            "renderer_config.workspace.objective.coefficients must contain every variable ID exactly once."
        )
    for variable_id, coefficient in coefficients.items():
        _number(coefficient, f"renderer_config.workspace.objective.coefficients.{variable_id}")
    for field in ("label", "currency"):
        if field in objective and not isinstance(objective[field], str):
            raise ExperimentDefinitionError(f"renderer_config.workspace.objective.{field} must be a string.")

    constraints = workspace.get("constraints")
    if not isinstance(constraints, list) or not 1 <= len(constraints) <= 50:
        raise ExperimentDefinitionError("renderer_config.workspace.constraints must contain 1 to 50 constraints.")
    constraint_ids = []
    for index, constraint in enumerate(constraints):
        path = f"renderer_config.workspace.constraints[{index}]"
        if not isinstance(constraint, dict):
            raise ExperimentDefinitionError(f"{path} must be an object.")
        constraint_id = constraint.get("id")
        _workspace_id(constraint_id, f"{path}.id")
        constraint_ids.append(constraint_id)
        if constraint.get("operator") not in {"<=", ">="}:
            raise ExperimentDefinitionError(f"{path}.operator must be <= or >=.")
        _number(constraint.get("rhs"), f"{path}.rhs")
        coefficients = constraint.get("coefficients")
        if not isinstance(coefficients, dict) or set(coefficients) != set(variable_ids):
            raise ExperimentDefinitionError(
                f"{path}.coefficients must contain every variable ID exactly once."
            )
        for variable_id, coefficient in coefficients.items():
            _number(coefficient, f"{path}.coefficients.{variable_id}")
        if "label" in constraint:
            _non_empty_string(constraint["label"], f"{path}.label")
    if len(set(constraint_ids)) != len(constraint_ids):
        raise ExperimentDefinitionError("renderer_config.workspace constraint IDs must be unique.")

    for field in ("title", "problem_statement"):
        if field in workspace:
            _non_empty_string(workspace[field], f"renderer_config.workspace.{field}")


def _validate_multivariable_profit_workspace(workspace):
    if not isinstance(workspace, dict):
        raise ExperimentDefinitionError("renderer_config.workspace must be an object.")
    if workspace.get("type") != "multivariable_profit":
        raise ExperimentDefinitionError("renderer_config.workspace.type must be multivariable_profit.")
    if type(workspace.get("version")) is not int or workspace["version"] != 1:
        raise ExperimentDefinitionError("renderer_config.workspace.version must be 1.")

    for field in ("title", "scenario", "currency"):
        _non_empty_string(workspace.get(field), f"renderer_config.workspace.{field}")

    products = workspace.get("products")
    if not isinstance(products, list) or len(products) != 2:
        raise ExperimentDefinitionError("renderer_config.workspace.products must contain exactly two products.")
    product_ids = []
    price_drops = []
    for index, product in enumerate(products):
        path = f"renderer_config.workspace.products[{index}]"
        if not isinstance(product, dict):
            raise ExperimentDefinitionError(f"{path} must be an object.")
        product_id = product.get("id")
        _workspace_id(product_id, f"{path}.id")
        product_ids.append(product_id)
        for field in ("label", "unit"):
            _non_empty_string(product.get(field), f"{path}.{field}")
        for field in ("price", "price_drop", "unit_cost", "initial", "min", "max", "step"):
            _number(product.get(field), f"{path}.{field}")
        if product["price"] < 0 or product["unit_cost"] < 0:
            raise ExperimentDefinitionError(f"{path}.price and {path}.unit_cost must not be negative.")
        if product["price_drop"] <= 0:
            raise ExperimentDefinitionError(f"{path}.price_drop must be positive.")
        if product["min"] < 0 or product["min"] >= product["max"]:
            raise ExperimentDefinitionError(f"{path}.min must be non-negative and smaller than max.")
        if not product["min"] <= product["initial"] <= product["max"]:
            raise ExperimentDefinitionError(f"{path}.initial must be between min and max.")
        if product["step"] <= 0:
            raise ExperimentDefinitionError(f"{path}.step must be positive.")
        price_drops.append(product["price_drop"])
    if len(set(product_ids)) != len(product_ids):
        raise ExperimentDefinitionError("renderer_config.workspace product IDs must be unique.")

    _number(workspace.get("cross_effect"), "renderer_config.workspace.cross_effect")
    _number(workspace.get("fixed_cost"), "renderer_config.workspace.fixed_cost")
    if workspace["fixed_cost"] < 0:
        raise ExperimentDefinitionError("renderer_config.workspace.fixed_cost must not be negative.")
    determinant = 4 * price_drops[0] * price_drops[1] - workspace["cross_effect"] ** 2
    if determinant <= 1e-12:
        raise ExperimentDefinitionError(
            "renderer_config.workspace must describe one concave profit hill; "
            "reduce cross_effect or increase the price_drop values."
        )

    _number(workspace.get("target_tolerance"), "renderer_config.workspace.target_tolerance")
    if workspace["target_tolerance"] <= 0:
        raise ExperimentDefinitionError("renderer_config.workspace.target_tolerance must be positive.")

    steps = workspace.get("steps")
    if not isinstance(steps, list) or len(steps) != len(MULTIVARIABLE_STEP_KINDS):
        raise ExperimentDefinitionError(
            "renderer_config.workspace.steps must contain Hill, Slope, Walk, Result, and Question."
        )
    kinds = []
    for index, step in enumerate(steps):
        path = f"renderer_config.workspace.steps[{index}]"
        if not isinstance(step, dict):
            raise ExperimentDefinitionError(f"{path} must be an object.")
        kind = step.get("kind")
        if kind not in MULTIVARIABLE_STEP_KINDS:
            raise ExperimentDefinitionError(f"{path}.kind is not a supported workshop step.")
        kinds.append(kind)
        for field in ("title", "instruction"):
            _non_empty_string(step.get(field), f"{path}.{field}")
    if tuple(kinds) != MULTIVARIABLE_STEP_KINDS:
        raise ExperimentDefinitionError(
            "renderer_config.workspace.steps must be ordered as hill, slope, walk, result, question."
        )

    questions = workspace.get("questions")
    if not isinstance(questions, dict):
        raise ExperimentDefinitionError("renderer_config.workspace.questions must be an object.")
    slope_question = questions.get("slope")
    if not isinstance(slope_question, dict):
        raise ExperimentDefinitionError("renderer_config.workspace.questions.slope must be an object.")
    _non_empty_string(slope_question.get("prompt"), "renderer_config.workspace.questions.slope.prompt")
    options = slope_question.get("options")
    if not isinstance(options, list) or len(options) != 3:
        raise ExperimentDefinitionError(
            "renderer_config.workspace.questions.slope.options must contain increase, decrease, and same."
        )
    option_values = []
    for index, option in enumerate(options):
        path = f"renderer_config.workspace.questions.slope.options[{index}]"
        if not isinstance(option, dict) or option.get("value") not in SLOPE_DIRECTIONS:
            raise ExperimentDefinitionError(f"{path}.value must be increase, decrease, or same.")
        _non_empty_string(option.get("label"), f"{path}.label")
        option_values.append(option["value"])
    if set(option_values) != SLOPE_DIRECTIONS:
        raise ExperimentDefinitionError(
            "renderer_config.workspace.questions.slope.options must contain each direction exactly once."
        )

    reflection = questions.get("reflection")
    if not isinstance(reflection, dict):
        raise ExperimentDefinitionError("renderer_config.workspace.questions.reflection must be an object.")
    _non_empty_string(
        reflection.get("prompt"), "renderer_config.workspace.questions.reflection.prompt"
    )
    minimum = reflection.get("minimum_characters")
    if type(minimum) is not int or not 1 <= minimum <= 2000:
        raise ExperimentDefinitionError(
            "renderer_config.workspace.questions.reflection.minimum_characters must be an integer from 1 to 2000."
        )


def _validate_workspace(workspace):
    if not isinstance(workspace, dict):
        raise ExperimentDefinitionError("renderer_config.workspace must be an object.")
    workspace_type = workspace.get("type")
    if workspace_type == "linear_programming":
        _validate_linear_programming_workspace(workspace)
        return
    if workspace_type == "multivariable_profit":
        _validate_multivariable_profit_workspace(workspace)
        return
    raise ExperimentDefinitionError(
        "renderer_config.workspace.type must be linear_programming or multivariable_profit."
    )


def _validate_tracking(tracking):
    if not isinstance(tracking, dict):
        raise ExperimentDefinitionError("tracking must be an object.")

    watch_objects = tracking.get("watch_objects", [])
    if not isinstance(watch_objects, list) or any(
        not isinstance(name, str) or not name.strip() for name in watch_objects
    ):
        raise ExperimentDefinitionError("tracking.watch_objects must be a list of non-empty strings.")

    if "progress_object" in tracking:
        _non_empty_string(tracking["progress_object"], "tracking.progress_object")

    if "throttle_ms" in tracking:
        throttle_ms = tracking["throttle_ms"]
        if type(throttle_ms) is not int or not 250 <= throttle_ms <= 60000:
            raise ExperimentDefinitionError("tracking.throttle_ms must be an integer from 250 to 60000.")

    completion = tracking.get("completion")
    if completion is None:
        return
    if not isinstance(completion, dict):
        raise ExperimentDefinitionError("tracking.completion must be an object.")
    _non_empty_string(completion.get("object"), "tracking.completion.object")
    operator = completion.get("operator")
    if not isinstance(operator, str) or operator not in SUPPORTED_COMPLETION_OPERATORS:
        choices = ", ".join(sorted(SUPPORTED_COMPLETION_OPERATORS))
        raise ExperimentDefinitionError(f"tracking.completion.operator must be one of: {choices}.")
    if operator != "truthy" and "value" not in completion:
        raise ExperimentDefinitionError("tracking.completion.value is required for this operator.")
    scalar_types = (str, int, float, bool, type(None))
    if "value" in completion and not isinstance(completion["value"], scalar_types):
        raise ExperimentDefinitionError("tracking.completion.value must be a scalar JSON value.")


def _validate_graphspace_renderer_config(renderer_config):
    path = renderer_config.get("path")
    if path != "/graphspace/index_3.html":
        raise ExperimentDefinitionError(
            "renderer_config.path must be /graphspace/index_3.html for GraphSpace experiments."
        )
    for field in ("heading", "message"):
        _non_empty_string(renderer_config.get(field), f"renderer_config.{field}")
    if "note" in renderer_config:
        _non_empty_string(renderer_config["note"], "renderer_config.note")


def validate_experiment_configuration(configuration):
    """Validate the stable runtime envelope without removing extension fields."""
    if not isinstance(configuration, dict):
        raise ExperimentDefinitionError("configuration must be an object.")

    renderer = configuration.get("renderer")
    if renderer is None:
        # Older question-based experiment records predate the renderer envelope.
        return configuration

    if not isinstance(renderer, str) or renderer not in SUPPORTED_RENDERERS:
        choices = ", ".join(sorted(SUPPORTED_RENDERERS))
        raise ExperimentDefinitionError(f"renderer must be one of: {choices}.")
    if type(configuration.get("schema_version")) is not int or configuration["schema_version"] != 1:
        raise ExperimentDefinitionError("schema_version must be 1 when renderer is present.")

    renderer_config = configuration.get("renderer_config", {})
    if not isinstance(renderer_config, dict):
        raise ExperimentDefinitionError("renderer_config must be an object.")

    if renderer == "geogebra":
        material_id = renderer_config.get("material_id")
        workspace = renderer_config.get("workspace")
        if material_id is None and workspace is None:
            raise ExperimentDefinitionError(
                "renderer_config must provide either material_id or a supported workspace."
            )
        if material_id is not None:
            _non_empty_string(material_id, "renderer_config.material_id")
        if workspace is not None:
            _validate_workspace(workspace)
        if "app_name" in renderer_config:
            _non_empty_string(renderer_config["app_name"], "renderer_config.app_name")
        parameters = renderer_config.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ExperimentDefinitionError("renderer_config.parameters must be an object.")
        scalar_types = (str, int, float, bool, type(None))
        if any(not isinstance(key, str) or not isinstance(value, scalar_types) for key, value in parameters.items()):
            raise ExperimentDefinitionError("renderer_config.parameters may contain only scalar JSON values.")

    if renderer == "graphspace":
        _validate_graphspace_renderer_config(renderer_config)

    if "tracking" in configuration:
        _validate_tracking(configuration["tracking"])

    return configuration
