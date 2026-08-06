from django.conf import settings
from django.core.checks import Error, Tags, register


def _errors(*, deploy: bool) -> list[Error]:
    return [
        Error(message, id=f"ftl.E{index:03d}")
        for index, message in enumerate(
            settings.RUNTIME_SETTINGS.safe_validation_errors(deploy=deploy), start=1
        )
    ]


@register()
def runtime_configuration_check(**_kwargs: object) -> list[Error]:
    return _errors(deploy=False)


@register(Tags.security, deploy=True)
def production_configuration_check(**_kwargs: object) -> list[Error]:
    return _errors(deploy=True)
