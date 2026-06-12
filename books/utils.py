#utils.py

from django.core.exceptions import NON_FIELD_ERRORS


def add_service_errors(form, error):
    """
    Переносить ValidationError із service layer у Django-форму.
    """

    if hasattr(error, "message_dict"):
        for field_name, messages in error.message_dict.items():
            target_field = field_name

            if (
                field_name == NON_FIELD_ERRORS
                or field_name not in form.fields
            ):
                target_field = None

            for message in messages:
                form.add_error(target_field, message)

        return

    for message in error.messages:
        form.add_error(None, message)