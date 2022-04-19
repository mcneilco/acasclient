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
    an optional list of errors and warnings.
    Usage::

            messages = ['Invalid file type', 'Multiple structures found']
            val_res = ValidationResult(is_valid=True, messages=messages)

            if not val_res:
                print('\n'.join(val_res.get_messages()))

    """

    def __init__(self, is_valid: bool, messages: List[str] = None, errors: List[str] = None, warnings: List[str] = None):
        self._is_valid = is_valid
        self._errors = errors or []
        self._warnings = warnings or []
        # For simple messages, classify them as errors or warnings based on the validity of the result
        if messages:
            if is_valid:
                self._warnings += messages
            else:
                self._errors += messages
        # Check we are not in the invalid state of "valid" with errors
        if is_valid and self._errors:
            raise ValueError("ValidationResult cannot be valid and contain error messages")

    def __bool__(self) -> bool:
        return self._is_valid

    def __str__(self) -> str:
        res = 'VALID' if self._is_valid else 'INVALID'
        if self._errors:
            res += '\nERRORS:\n' + '\n'.join(self._errors)
        if self._warnings:
            res += '\nWARNINGS:\n' + '\n'.join(self._warnings)
        return res

    def __repr__(self) -> str:
        return str(repr)

    def __add__(self, other):
        is_valid = self._is_valid and other._is_valid
        errors = self._errors + other._errors
        warnings = self._warnings + other._warnings
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def get_messages(self) -> List[str]:
        return self._errors + self._warnings
    
    def get_errors(self) -> List[str]:
        return self._errors
    
    def get_warnings(self) -> List[str]:
        return self._warnings


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


def _dedupe_messages(messages: List[str]) -> List[str]:
    """
    Deduplicate messages and count occurrences.

    :param messages: list of messages
    :type messages: list

    :return: list of deduplicated messages
    :rtype: list
    """
    messages_dict = defaultdict(int)
    for msg in messages:
        messages_dict[msg] += 1
    deduped_messages = []
    for msg, count in messages_dict.items():
        if count > 1:
            deduped_messages.append(f'{count} occurrences of: {msg}')
        else:
            deduped_messages.append(msg)
    return deduped_messages

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
    has_errors = len(validation_result.get_errors()) > 0
    has_warnings = len(validation_result.get_warnings()) > 0
    
    # Deduplicate error and warning messages
    errors = _dedupe_messages(validation_result.get_errors())
    warnings = _dedupe_messages(validation_result.get_warnings())

    # Build error_messages list of dicts
    error_messages = []
    for msg in errors:
        error_messages.append({'message': msg, 'errorLevel': 'error'})
    for msg in warnings:
        error_messages.append({'message': msg, 'errorLevel': 'warning'})
    # Format HTML
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