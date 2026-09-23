"""Seed the complete, published "AI for Management" learning program.

The course uses Jeff Su's "AI Agents, Clearly Explained" as its anchor video:
https://youtu.be/FwOTs4UxQS4

Run with: python manage.py seed_ai_management
The command is intentionally idempotent and may be run again to refresh the seed data.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assessments.models import (
    CaseStudy,
    CaseStudyQuestion,
    LearningCheck,
    LearningCheckQuestion,
    Question,
    QuestionOption,
)
from content.models import ActivityContent, Experiment, Video
from curriculum.models import Chapter, Course, CourseVersion, LearningActivity, Program, PublishStatus, Subtopic
from media_library.models import MediaAsset


VIDEO_URL = "https://youtu.be/FwOTs4UxQS4"
VIDEO_DURATION_SECONDS = 610
SEED_PREFIX = "ai-management-v1"


CHAPTERS = [
    {
        "title": "From AI Answers to AI Action",
        "slug": "from-ai-answers-to-ai-action",
        "minutes": 45,
        "description": "Distinguish language models, fixed AI workflows, and autonomous agents in management terms.",
        "subtopics": [
            {
                "title": "The three levels of AI",
                "slug": "three-levels-of-ai",
                "objectives": ["Differentiate an LLM, an AI workflow, and an AI agent", "Match each level to an appropriate business task"],
                "activities": [
                    ("CONCEPT_VIDEO", "Watch: AI Agents, Clearly Explained", 12, "Watch the anchor video and note what changes at each level."),
                    ("CONCEPT_OVERVIEW", "Manager's map of the three levels", 8, "Connect response generation, fixed orchestration, and autonomous decisions to workplace examples."),
                ],
            },
            {
                "title": "Choosing the right level",
                "slug": "choosing-the-right-level",
                "objectives": ["Avoid unnecessary autonomy", "Select an AI pattern using task variability and risk"],
                "activities": [
                    ("INTERACTIVE", "Sort the management tasks", 10, "Classify common tasks as LLM, workflow, agent, or no-AI candidates."),
                    ("ASSIGNMENT", "Build your AI opportunity list", 15, "Identify three recurring team tasks and justify the appropriate AI level for each."),
                ],
            },
        ],
        "questions": [
            ("MCQ", "What most clearly distinguishes an AI agent from a fixed AI workflow?", ["It always writes longer responses", "It uses an LLM to choose actions dynamically", "It never needs access to tools", "It follows only a manager-written decision tree"], 1, "Agents use model-based reasoning to decide the next action instead of following only a predetermined path."),
            ("TRUE_FALSE", "A predictable, rules-based approval process always requires a fully autonomous AI agent.", ["True", "False"], 1, "A deterministic workflow is usually more controllable and appropriate for predictable processes."),
            ("MCQ", "Which task is the best initial fit for a basic LLM?", ["Drafting a meeting summary from supplied notes", "Issuing customer refunds without review", "Changing payroll records", "Purchasing inventory autonomously"], 0, "Drafting from supplied context is a bounded generation task that does not require autonomous action."),
        ],
    },
    {
        "title": "Grounded Workflows and Reliable Context",
        "slug": "grounded-workflows-and-reliable-context",
        "minutes": 50,
        "description": "Use retrieval and structured workflows to make AI outputs more relevant, repeatable, and auditable.",
        "subtopics": [
            {
                "title": "RAG for managers",
                "slug": "rag-for-managers",
                "objectives": ["Explain retrieval-augmented generation in plain language", "Recognize when proprietary context is required"],
                "activities": [
                    ("READING", "Why internal context changes the answer", 10, "Learn how retrieval supplies current, approved business information before generation."),
                    ("EXPERIMENT", "Ground the policy answer", 15, "Compare an ungrounded response with one based on an approved policy excerpt."),
                ],
            },
            {
                "title": "Designing repeatable workflows",
                "slug": "designing-repeatable-workflows",
                "objectives": ["Map a fixed sequence of AI-assisted steps", "Add verification and escalation points"],
                "activities": [
                    ("OBSERVE_LEARN_PRACTICE", "Map an AI-assisted reporting workflow", 15, "Turn a recurring reporting task into inputs, transformations, checks, and outputs."),
                    ("HOMEWORK", "Create a workflow control sheet", 10, "Document owners, approved data sources, failure modes, and handoffs."),
                ],
            },
        ],
        "questions": [
            ("MCQ", "What does retrieval-augmented generation add before an LLM produces an answer?", ["Relevant information retrieved from an approved source", "A guarantee that every answer is correct", "Permanent memory of every employee", "Permission to take any action"], 0, "RAG retrieves relevant context and includes it in the model input; it does not guarantee truth or grant authority."),
            ("MULTI_SELECT", "Which controls improve a management workflow? Select all that apply.", ["Approved source data", "A defined escalation path", "Unlimited system permissions", "Output validation"], [0, 1, 3], "Grounded data, validation, and escalation improve reliability; permissions should be least-privilege."),
            ("TRUE_FALSE", "RAG can help an AI system use current company information that was not part of its original training.", ["True", "False"], 0, "Retrieval can supply relevant current or proprietary documents at run time."),
        ],
    },
    {
        "title": "How Agents Plan, Act, and Improve",
        "slug": "how-agents-plan-act-and-improve",
        "minutes": 90,
        "description": "Understand goals, tools, the ReAct loop, reflection, and the trade-off between autonomy and control.",
        "subtopics": [
            {
                "title": "The agent loop",
                "slug": "the-agent-loop",
                "objectives": ["Describe the reason-act-observe cycle", "Identify the role of tools and feedback"],
                "activities": [
                    ("CONCEPT_OVERVIEW", "ReAct without the jargon", 10, "Follow how an agent reasons, calls a tool, observes the result, and selects its next step."),
                    ("SIMULATION", "Run the inbox-priority agent", 20, "Choose tools and next actions for an agent handling an ambiguous executive request."),
                    ("EXPERIMENT", "Build an agent experiment model", 15, "Model a bounded agent experiment by defining its goal, inputs, tools, decision loop, human checkpoint, and success measure."),
                    ("EXPERIMENT", "Map AI agent value and risk in GraphSpace", 20, "Use a 3D decision surface to explore how business value, autonomy, and risk change an AI agent pilot recommendation."),
                ],
            },
            {
                "title": "Goals, tools, and boundaries",
                "slug": "goals-tools-and-boundaries",
                "objectives": ["Write a measurable agent goal", "Set tool access and stopping conditions"],
                "activities": [
                    ("INTERACTIVE_WORKSHOP", "Write an agent charter", 15, "Define the goal, allowed data, tools, checkpoints, stopping rules, and accountable owner."),
                    ("FLASHCARD", "Agent architecture essentials", 10, "Review goal, model, memory, retrieval, tools, planning, observation, and guardrails."),
                ],
            },
        ],
        "questions": [
            ("MCQ", "In a ReAct-style loop, what should happen after an agent uses a tool?", ["It observes the result and reassesses the next step", "It always ends the task", "It deletes its goal", "It grants itself more permissions"], 0, "The observation informs the agent's next reasoning and action."),
            ("MCQ", "Which agent charter is best defined?", ["Improve everything as quickly as possible", "Resolve standard support requests using the knowledge base; escalate refunds and low-confidence cases", "Do whatever customers request", "Use every available system until the problem disappears"], 1, "A useful charter includes scope, sources, boundaries, and escalation conditions."),
            ("TRUE_FALSE", "Giving an agent more tools and permissions always makes it more effective.", ["True", "False"], 1, "Extra access increases the action surface and risk; tools should be limited to what the goal requires."),
        ],
    },
    {
        "title": "Managing AI Agents Responsibly",
        "slug": "managing-ai-agents-responsibly",
        "minutes": 60,
        "description": "Evaluate agent opportunities, install governance, and launch a measurable, human-supervised pilot.",
        "subtopics": [
            {
                "title": "Risk and human oversight",
                "slug": "risk-and-human-oversight",
                "objectives": ["Assess impact, reversibility, and confidence", "Place meaningful human approval gates"],
                "activities": [
                    ("READING", "The autonomy risk matrix", 10, "Use impact and reversibility to decide whether AI may recommend, draft, or act."),
                    ("INTERACTIVE", "Place the approval gates", 15, "Add human review to hiring, finance, customer, and operational scenarios."),
                ],
            },
            {
                "title": "Pilot and measure",
                "slug": "pilot-and-measure",
                "objectives": ["Define success and safety metrics", "Create a phased adoption plan"],
                "activities": [
                    ("PROJECT", "Design a 30-day agent pilot", 25, "Prepare a narrow pilot with baseline, owner, test set, approvals, metrics, and rollback plan."),
                    ("ASSIGNMENT", "Executive decision memo", 10, "Recommend proceed, revise, or stop based on value, risk, evidence, and organizational readiness."),
                ],
            },
        ],
        "questions": [
            ("MCQ", "Where is a human approval gate most important?", ["Before a high-impact, hard-to-reverse action", "Before correcting punctuation", "Before retrieving a public webpage", "Before formatting a draft"], 0, "Human review is most valuable when impact is high or an action is difficult to reverse."),
            ("MULTI_SELECT", "Which measures belong in an agent pilot? Select all that apply.", ["Task success rate", "Escalation and error rate", "Time or cost saved", "Number of fashionable AI terms used"], [0, 1, 2], "A pilot should measure value, quality, and risk—not hype."),
            ("TRUE_FALSE", "A pilot should have a named accountable owner and a rollback plan.", ["True", "False"], 0, "Ownership and rollback are basic controls for safe experimentation."),
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed the published "AI for Management" program, course content, activities, and assessments.'

    @transaction.atomic
    def handle(self, *args, **options):
        program, _ = Program.objects.update_or_create(
            code="ai-for-management",
            defaults={
                "name": "AI for Management",
                "description": "A practical management program for selecting, governing, and piloting AI workflows and agents.",
                "grade": "Professional",
                "status": PublishStatus.PUBLISHED,
            },
        )
        course, _ = Course.objects.update_or_create(
            code="ai-agents-for-managers",
            defaults={
                "program": program,
                "name": "AI Agents for Managers",
                "description": "Move from AI concepts to a governed 30-day agent pilot using a concise video-led learning journey.",
                "status": PublishStatus.PUBLISHED,
                "display_order": 1,
            },
        )
        version, _ = CourseVersion.objects.update_or_create(
            course=course,
            version_number=1,
            defaults={"name": "Foundation Edition", "status": PublishStatus.PUBLISHED, "published_at": timezone.now()},
        )
        media, _ = MediaAsset.objects.update_or_create(
            storage_path="external/youtube/FwOTs4UxQS4",
            defaults={
                "file_name": "AI Agents, Clearly Explained (Jeff Su)",
                "file_type": "VIDEO",
                "mime_type": "text/html",
                "file_size": 0,
                "cdn_url": VIDEO_URL,
                "duration_seconds": VIDEO_DURATION_SECONDS,
                "status": MediaAsset.Status.READY,
            },
        )

        counts = {"chapters": 0, "subtopics": 0, "activities": 0, "questions": 0}
        for chapter_order, chapter_data in enumerate(CHAPTERS, start=1):
            chapter, _ = Chapter.objects.update_or_create(
                course_version=version,
                slug=chapter_data["slug"],
                defaults={
                    "title": chapter_data["title"],
                    "description": chapter_data["description"],
                    "chapter_number": chapter_order,
                    "estimated_minutes": chapter_data["minutes"],
                    "is_required": True,
                    "status": PublishStatus.PUBLISHED,
                    "display_order": chapter_order,
                    "completion_rule": {"required_subtopics": True, "learning_check_required": True},
                },
            )
            counts["chapters"] += 1
            for subtopic_order, subtopic_data in enumerate(chapter_data["subtopics"], start=1):
                subtopic, _ = Subtopic.objects.update_or_create(
                    chapter=chapter,
                    slug=subtopic_data["slug"],
                    defaults={
                        "title": subtopic_data["title"],
                        "description": subtopic_data["objectives"][0],
                        "learning_objectives": subtopic_data["objectives"],
                        "estimated_minutes": sum(item[2] for item in subtopic_data["activities"]),
                        "display_order": subtopic_order,
                        "is_required": True,
                        "status": PublishStatus.PUBLISHED,
                    },
                )
                counts["subtopics"] += 1
                for activity_order, (activity_type, title, minutes, description) in enumerate(subtopic_data["activities"], start=1):
                    activity, _ = LearningActivity.objects.update_or_create(
                        subtopic=subtopic,
                        display_order=activity_order,
                        defaults={
                            "activity_type": activity_type,
                            "title": title,
                            "description": description,
                            "is_required": True,
                            "estimated_minutes": minutes,
                            "completion_rule": {"complete": True},
                            "status": PublishStatus.PUBLISHED,
                        },
                    )
                    self._seed_activity_content(activity, chapter_order, subtopic_order, media)
                    counts["activities"] += 1

            learning_check, _ = LearningCheck.objects.update_or_create(
                chapter=chapter,
                defaults={
                    "title": f"{chapter_data['title']} — Learning Check",
                    "instructions": "Answer all three questions. Review the explanations before trying again.",
                    "passing_score": Decimal("70"),
                    "max_attempts": 3,
                    "time_limit_minutes": 10,
                    "randomize_questions": False,
                    "status": PublishStatus.PUBLISHED,
                },
            )
            for question_order, question_data in enumerate(chapter_data["questions"], start=1):
                question = self._upsert_question(chapter, question_order, question_data)
                LearningCheckQuestion.objects.update_or_create(
                    learning_check=learning_check,
                    question=question,
                    defaults={"display_order": question_order, "marks": question.marks, "is_required": True},
                )
                counts["questions"] += 1

        self._seed_case_study(version)
        self.stdout.write(self.style.SUCCESS("AI for Management seed completed."))
        self.stdout.write(f"Program: {program.name} ({program.id})")
        self.stdout.write(f"Course: {course.name} ({course.id})")
        self.stdout.write(
            f"Created/refreshed {counts['chapters']} chapters, {counts['subtopics']} subtopics, "
            f"{counts['activities']} activities, and {counts['questions']} learning-check questions."
        )

    def _seed_activity_content(self, activity, chapter_order, subtopic_order, media):
        if activity.activity_type == LearningActivity.ActivityType.CONCEPT_VIDEO:
            Video.objects.update_or_create(
                activity=activity,
                defaults={
                    "media_asset": media,
                    "title": "AI Agents, Clearly Explained",
                    "description": "Jeff Su's non-technical explanation of LLMs, AI workflows, RAG, ReAct, and AI agents.",
                    "duration_seconds": VIDEO_DURATION_SECONDS,
                    "transcript": "",
                    "captions": [],
                    "completion_percentage": 90,
                },
            )
            activity.completion_rule = {"watch_percentage": 90}
            activity.save(update_fields=["completion_rule", "updated_at"])
            return

        content = {
            "source": {"title": "AI Agents, Clearly Explained", "creator": "Jeff Su", "url": VIDEO_URL},
            "chapter": chapter_order,
            "section": subtopic_order,
            "facilitation": {
                "prompt": activity.description,
                "deliverable": "Record a concise response, decision, or artefact in the learning journal.",
                "reflection": "What must remain a human decision, and why?",
            },
        }
        ActivityContent.objects.update_or_create(activity=activity, defaults={"content_type": "application/json", "content": content})
        if activity.activity_type in {LearningActivity.ActivityType.EXPERIMENT, LearningActivity.ActivityType.SIMULATION}:
            experiment_type = Experiment.ExperimentType.QUESTION_BASED
            response_fields = ["decision", "rationale", "risk", "human_checkpoint"]
            if activity.title == "Build an agent experiment model":
                response_fields = ["goal", "inputs", "tools", "decision_loop", "human_checkpoint", "success_measure"]
            configuration = {"response_fields": response_fields}
            if activity.title == "Map AI agent value and risk in GraphSpace":
                experiment_type = Experiment.ExperimentType.HTML_INTERACTIVE
                configuration = {
                    "schema_version": 1,
                    "renderer": "graphspace",
                    "renderer_config": {
                        "path": "/graphspace/index_3.html",
                        "heading": "AI agent value-risk decision surface",
                        "message": "Open GraphSpace and graph z=(x*y)/10, where x is expected business value and y is autonomy. Compare the surface against operational risk before recommending a pilot boundary.",
                        "note": "Keep x and y between 0 and 10. Use the resulting surface as evidence for a bounded pilot, not as an automated approval decision.",
                    },
                }
            Experiment.objects.update_or_create(
                activity=activity,
                defaults={
                    "experiment_type": experiment_type,
                    "instructions": activity.description,
                    "configuration": configuration,
                    "external_url": None,
                },
            )

    def _upsert_question(self, chapter, question_order, data):
        question_type, text, options, correct, explanation = data
        seed_key = f"{SEED_PREFIX}:chapter-{chapter.chapter_number}:question-{question_order}"
        question = Question.objects.filter(metadata__seed_key=seed_key).first() or Question(metadata={"seed_key": seed_key})
        question.question_type = question_type
        question.question_text = text
        question.explanation = explanation
        question.difficulty = "MEDIUM"
        question.marks = Decimal("1")
        question.subject = "AI for Management"
        question.grade = "Professional"
        question.chapter = chapter
        question.subtopic = None
        question.metadata = {"seed_key": seed_key, "source_video": VIDEO_URL}
        question.status = PublishStatus.PUBLISHED
        question.save()

        correct_indexes = set(correct if isinstance(correct, list) else [correct])
        QuestionOption.objects.filter(question=question).exclude(display_order__in=range(len(options))).delete()
        for index, option_text in enumerate(options):
            QuestionOption.objects.update_or_create(
                question=question,
                display_order=index,
                defaults={
                    "option_text": option_text,
                    "is_correct": index in correct_indexes,
                    "explanation": explanation if index in correct_indexes else "Revisit the chapter and compare the level of autonomy, context, and risk.",
                },
            )
        return question

    def _seed_case_study(self, version):
        chapter = version.chapters.get(slug="managing-ai-agents-responsibly")
        case_study, _ = CaseStudy.objects.update_or_create(
            chapter=chapter,
            defaults={
                "title": "Should Northstar deploy an autonomous service agent?",
                "introduction": "A regional services company wants an agent to reduce response time, but the proposed system can access customer records and issue credits.",
                "content": {
                    "scenario": "The current team handles 1,200 requests weekly. Sixty percent are repetitive, while billing disputes and account changes carry material risk.",
                    "evidence": ["Median response time: 19 hours", "Knowledge-base coverage: 72%", "Billing error cost last quarter: $38,000"],
                    "task": "Recommend a bounded pilot, including scope, tools, approval gates, metrics, and rollback triggers.",
                },
                "estimated_minutes": 20,
                "passing_score": Decimal("70"),
                "status": PublishStatus.PUBLISHED,
            },
        )
        seed_key = f"{SEED_PREFIX}:case-study"
        question = Question.objects.filter(metadata__seed_key=seed_key).first() or Question(metadata={"seed_key": seed_key})
        question.question_type = Question.QuestionType.LONG_TEXT
        question.question_text = "Write the executive recommendation for Northstar's pilot. Address value, scope, data, human oversight, metrics, and stop conditions."
        question.explanation = "Strong recommendations connect a narrow business outcome to explicit controls and measurable evidence."
        question.difficulty = "HARD"
        question.marks = Decimal("6")
        question.subject = "AI for Management"
        question.grade = "Professional"
        question.chapter = chapter
        question.metadata = {"seed_key": seed_key, "rubric": {"value": 1, "scope": 1, "data": 1, "oversight": 1, "metrics": 1, "stop_conditions": 1}}
        question.status = PublishStatus.PUBLISHED
        question.save()
        CaseStudyQuestion.objects.update_or_create(
            case_study=case_study,
            question=question,
            defaults={"display_order": 1, "marks": Decimal("6"), "is_required": True},
        )
