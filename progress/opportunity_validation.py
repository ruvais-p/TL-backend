from urllib.parse import urlparse

from django.utils import timezone

from media_library.models import MediaAsset
from progress.models import CareerOpportunity


ISO_4217_CODES = frozenset(
    """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB
    BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUC
    CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF
    GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF
    KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP
    MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP
    PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD
    SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI
    UYU UYW UZS VED VES VND VUV WST XAF XAG XAU XBA XBB XBC XBD XCD XDR XOF
    XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWL
    """.split()
) - {"XXX"}


def _value(attrs, instance, field):
    if field in attrs:
        return attrs[field]
    return getattr(instance, field, None) if instance is not None else None


def validate_opportunity(attrs, *, instance=None, require_complete=False):
    errors = {}

    def value(field):
        return _value(attrs, instance, field)

    if require_complete:
        for field in ("title", "company_name", "summary", "description_markdown"):
            if not value(field):
                errors[field] = "This field is required before publication."

    workplace_mode = value("workplace_mode")
    if workplace_mode == CareerOpportunity.WorkplaceMode.REMOTE:
        if require_complete and not value("remote_region"):
            errors["remote_region"] = (
                "State the permitted applicant region before publication."
            )
    elif workplace_mode in {
        CareerOpportunity.WorkplaceMode.HYBRID,
        CareerOpportunity.WorkplaceMode.IN_OFFICE,
    }:
        if require_complete and not value("physical_location"):
            errors["physical_location"] = (
                "A physical location is required for this workplace mode."
            )

    disclosure = value("compensation_disclosure")
    minimum = value("compensation_min")
    maximum = value("compensation_max")
    currency = (value("compensation_currency") or "").upper()
    pay_period = value("compensation_pay_period")
    if disclosure == CareerOpportunity.CompensationDisclosure.PAID:
        if require_complete and minimum is None and maximum is None:
            errors["compensation_min"] = "Provide at least one compensation amount."
        if (minimum is not None or maximum is not None or require_complete) and currency not in ISO_4217_CODES:
            errors["compensation_currency"] = "Use a valid three-letter ISO 4217 currency."
        if (minimum is not None or maximum is not None or require_complete) and not pay_period:
            errors["compensation_pay_period"] = "Select a pay period for paid compensation."
    elif any(item not in (None, "") for item in (minimum, maximum, currency, pay_period)):
        errors["compensation_disclosure"] = (
            "Compensation amounts are only allowed when disclosure is PAID."
        )
    if minimum is not None and minimum < 0:
        errors["compensation_min"] = "Compensation cannot be negative."
    if maximum is not None and maximum < 0:
        errors["compensation_max"] = "Compensation cannot be negative."
    if minimum is not None and maximum is not None and maximum < minimum:
        errors["compensation_max"] = "Maximum compensation cannot be lower than minimum."

    application_mode = value("application_mode")
    application_url = value("application_url") or ""
    if application_mode == CareerOpportunity.ApplicationMode.EXTERNAL:
        if require_complete and not application_url:
            errors["application_url"] = (
                "An HTTPS application URL is required before publication."
            )
        elif application_url and urlparse(application_url).scheme.lower() != "https":
            errors["application_url"] = "External application URLs must use HTTPS."
    elif application_url:
        errors["application_url"] = (
            "Remove the external URL or select EXTERNAL application mode."
        )

    deadline = value("application_deadline")
    if require_complete and deadline and deadline <= timezone.now():
        errors["application_deadline"] = "The application deadline must be in the future."

    logo = value("company_logo")
    if logo is not None and (
        logo.status != MediaAsset.Status.READY
        or not logo.mime_type.lower().startswith("image/")
    ):
        errors["company_logo"] = "Select a ready image media asset."

    return errors
