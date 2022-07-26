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

    def __init__(self, is_valid: bool, messages: List[str] = None, errors: List[str] = None, warnings: List[str] = None, summaries: List[str] = None):
        self._is_valid = is_valid
        self._errors = errors or []
        self._warnings = warnings or []
        self._summaries = summaries or []
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
        if self._summaries:
            res += '\nSUMMARIES:\n' + '\n'.join(self._summaries)
        return res

    def __repr__(self) -> str:
        return str(repr)

    def __add__(self, other):
        is_valid = self._is_valid and other._is_valid
        errors = self._errors + other._errors
        warnings = self._warnings + other._warnings
        summaries = self._summaries + other._summaries
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings, summaries=summaries)

    def get_messages(self) -> List[str]:
        return self._errors + self._warnings + self._summaries
    
    def get_errors(self) -> List[str]:
        return self._errors
    
    def get_warnings(self) -> List[str]:
        return self._warnings
    
    def get_summaries(self) -> List[str]:
        return self._summaries


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

def get_validation_response(validation_result, ls_thing=None, commit=False, transaction_id=-1) -> dict:
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
    errors = validation_result.get_errors()
    warnings = validation_result.get_warnings()
    summaries = validation_result.get_summaries()
    
    has_errors = len(errors) > 0
    has_warnings = len(warnings) > 0
    
    # Deduplicate error and warning messages
    errors = _dedupe_messages(errors)
    warnings = _dedupe_messages(warnings)

    # Build error_messages list of dicts
    error_messages = []
    for msg in errors:
        error_messages.append({'message': msg, 'errorLevel': 'error'})
    for msg in warnings:
        error_messages.append({'message': msg, 'errorLevel': 'warning'})
    # Format HTML
    html_summary = _get_html_summary(errors, warnings, summaries, commit)
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


def _get_html_summary(errors, warnings, summaries, commit) -> str:
    """
    Format HTML summary for the validation result.
    """
    # Lay out HTML template structure
    HTML_SUMMARY_TEMPLATE = """<p>{instructions}</p>
    {errors_block}
    {warnings_block}
    {summary_block}
    """
    ERRORS_TEMPLATE = """<h4 style=\"color:red\">Errors: {count} </h4>
    <ul>{message_list}</ul>
    """
    WARNINGS_TEMPLATE = """<h4>Warnings: {count} </h4>
    <p>Warnings provide information on issues found in the uploaded data. You can proceed with warnings; however, it is recommended that, if possible, you make the changes suggested by the warnings and upload a new version of the data by using the 'Back' button at the bottom of this screen.<p>
    <ul>{message_list}</ul>"""
    SUMMARY_TEMPLATE = """<h4>Summary</h4>
    <p>Information:</p>
    <ul>{message_list}</ul>"""
    MESSAGE_TEMPLATE = """<li>{message}</li>"""

    # Set up variables
    instructions = ''
    errors_block = ''
    warnings_block = ''
    summary_block = ''
    if errors:
        error_messages = '\n'.join(
            [MESSAGE_TEMPLATE.format(message=error) for error in errors])
        errors_block = ERRORS_TEMPLATE.format(
            count=len(errors), message_list=error_messages)
    if warnings:
        warnings_messages = '\n'.join(
            [MESSAGE_TEMPLATE.format(message=warning) for warning in warnings])
        warnings_block = WARNINGS_TEMPLATE.format(
            count=len(warnings), message_list=warnings_messages)
    if summaries:
        summary_messages = '\n'.join(
            [MESSAGE_TEMPLATE.format(message=summary) for summary in summaries])
        summary_block = SUMMARY_TEMPLATE.format(message_list=summary_messages)
    if commit:
        instructions = 'Upload completed.'
        # hide warnings and errors if we've already committed
        errors_block = ''
        warnings_block = ''
    elif errors:
        instructions = "Please fix the following errors and use the 'Back' button at the bottom of this screen to upload a new version of the data."
    elif warnings:
        instructions = "Please review the warnings and summary before uploading."
    else:
        instructions = "Please review the summary before uploading."
    # Format HTML
    html_summary = HTML_SUMMARY_TEMPLATE.format(
        instructions=instructions,
        errors_block=errors_block,
        warnings_block=warnings_block,
        summary_block=summary_block)
    return html_summary