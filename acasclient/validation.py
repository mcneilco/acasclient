import decorator
from collections import defaultdict
from typing import List

# Author: Anand Kumar

################################################################################
# Validation Result
################################################################################


class ValidationResult(object):
    """
    Class stores the validation results data. Each validation result stores
     an optional list of messages.
    Usage::

            messages = ['Invalid file type', 'Multiple structures found']
            val_res = ValidationResult(is_valid=True, messages=messages)

            if not val_res:
                print('\n'.join(val_res.get_messages()))

    """

    def __init__(self, is_valid: bool, messages: List[str] = None):
        self._is_valid = is_valid
        self._messages = messages or []

    def __bool__(self) -> bool:
        return self._is_valid

    def __str__(self) -> str:
        messages = '\n'.join(self._messages)
        if self._is_valid and messages == '':
            return 'VALID'
        elif self._is_valid:
            return 'VALID(Warnings): ' + messages
        elif messages == '':
            return 'INVALID'
        else:
            return 'INVALID(Errors): ' + messages

    def __repr__(self) -> str:
        return str(repr)

    def __add__(self, other):
        is_valid = self._is_valid and other._is_valid
        messages = self._messages + other._messages
        return ValidationResult(is_valid=is_valid, messages=messages)

    def get_messages(self) -> List[str]:
        return self._messages


@decorator.decorator
def validation_result(func, *args, **kwargs):
    """
    Encapsulate `func` returned values inside `ValidationResult`.

    :return: Validation result.
    :rtype: ValidationResult
    :raises TypeError: If `func` doesn't return a bool or a tuple or
            ValidationResult.
    """

    result = func(*args, **kwargs)

    if result is None:
        result = True

    if isinstance(result, bool):
        return ValidationResult(is_valid=result)
    elif isinstance(result, tuple):
        is_valid = result[0]
        messages = []
        if len(result) > 1:
            _messages = result[1]
            if isinstance(_messages, list):
                messages = _messages
            elif isinstance(_messages, str):
                messages = [_messages]
            else:
                raise TypeError("Expected a tuple of a boolean and "
                                f"list/str, got '{_messages}'")
        return ValidationResult(is_valid=is_valid, messages=messages)
    elif isinstance(result, ValidationResult):
        return result

    raise TypeError(f"Expected bool or tuple return values, got '{result}'")

def get_validation_response(validation_result, ls_thing=None, commit=False, transaction_id=-1):
    """
    :param validation_result: validation result object
    :type validation_result: validations.ValidationResult

    :param ls_thing: ls_thing of an entity
    :type ls_thing: dict

    :param commit: if the data was committed to the database
    :type commit: bool

    :param transaction_id: id of the transaction
    :type transaction_id: int

    :return: validation response for the given result
    :rtype: dict
    """
    # TODO: For now lets just categorise all messages with the same errorLevel.
    has_errors = not bool(validation_result)
    has_warnings = not has_errors and len(validation_result.get_messages()) > 0
    if has_errors:
        error_level = 'error'
    elif has_warnings:
        error_level = 'warning'
    else:
        error_level = ''
    
    # Deduplicate error messages and count occurrences
    messages = defaultdict(int)
    for msg in validation_result.get_messages():
        messages[msg] += 1
    
    deduped_errors = []
    for msg, count in messages.items():
        if count > 1:
            deduped_errors.append(f'{count} occurrences of: {msg}')
        else:
            deduped_errors.append(msg)

    error_messages = [{
        'errorLevel': error_level,
        'message': msg
    } for msg in deduped_errors]
    response_html_header = 'Validation ' + (
        'Successful' if bool(validation_result) else 'Unsuccessful')
    html_summary = f'<h3>{response_html_header}</h3>'
    for err_msg in error_messages:
        html_summary += f'<p>{err_msg["message"]}</p>'
    resp_dict = {
        'commit': commit,
        'transaction_id': transaction_id,
        'results': {
            'htmlSummary': html_summary,
        },
        'hasError': has_errors,
        'hasWarning': has_warnings,
        'errorMessages': error_messages,
    }
    if ls_thing:
        resp_dict['results']['thing'] = ls_thing
    return resp_dict