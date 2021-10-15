from __future__ import unicode_literals
from typing import Any, Dict
from .interactions import INTERACTION_VERBS_DICT, opposite

import copy
import hashlib
import json
import logging
import pathlib
from pathlib import Path
import re
from collections import defaultdict
from datetime import datetime
import pandas as pd
from six import text_type as str

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


ROW_NUM_KEY = 'row number'

# JSON encoding / decoding


def camel_to_underscore(name):
    """Convert string from camelCase to snake_case

    :param name: camelCase string to convert
    :type name: str
    :return: equivalent string in snake_case
    :rtype: str
    """
    camel_pat = re.compile(r'([A-Z])')
    return camel_pat.sub(lambda x: '_' + x.group(1).lower(), name)


def underscore_to_camel(name):
    """Convert string from snake_case to camelCase

    :param name: snake_case string to convert
    :type name: str
    :return: equivalent string in camelCase
    :rtype: str
    """
    under_pat = re.compile(r'_([a-z])')
    return under_pat.sub(lambda x: x.group(1).upper(), name)


def convert_json(data, convert):
    """Convert the keys within a nested dictionary data structure using the function passed to convert

    :param data: Data structure to be converted. Either a dict or a list.
    :type data: Union[dict, list]
    :param convert: Function to run on dict keys
    :type convert: func(str) -> str
    :raises ValueError: if datatype cannot be converted
    :return: Same data structure with keys converted by function passed as `convert` argument
    :rtype: Union[dict, list]
    """
    if type(data) is list:
        new_data = []
        for val in data:
            new_data.append(convert_json(val, convert) if (
                isinstance(val, dict) or isinstance(val, list)) else val)
    elif isinstance(data, dict):
        new_data = {}
        for key, val in data.items():
            new_data[convert(key)] = convert_json(val, convert) if (
                isinstance(val, dict) or isinstance(val, list)) else val
    else:
        raise ValueError(
            "Cannot convert {} to JSON: {}".format(type(data), data))
    return new_data


def datetime_to_ts(date):
    """Convert a datetime object to Unix timestamp *in milliseconds*
    Intended to generate Javascript-compatible millisecond timestamps.

    :param date: Date as a `datetime` instance
    :type date: datetime
    :return: Timestamp in milliseconds
    :rtype: int
    """
    if date is None:
        return None
    return int(date.timestamp() * 1000)


def ts_to_datetime(ts):
    """Convert a timestamp in milliseconds into a python `datetime` object

    :param ts: Timestamp in milliseconds
    :type ts: int
    :return: Datetime as a python `datetime`
    :rtype: datetime
    """
    if ts is None:
        return None
    return datetime.fromtimestamp(ts / 1000)


# ACAS-specific conversion helpers
def parse_states_into_dict(ls_states_dict):
    """Parse a dict of LsStates with nested LsValues into a simpler dict of { state_kind: { value_kind: value} }

    :param ls_states_dict: Dict of state_kind: LsState
    :type ls_states_dict: dict
    :return: Dictionary of state_kind: { value_kind: value }
    :rtype: dict
    """
    state_dict = {}
    for state_kind, state in ls_states_dict.items():
        state_dict[state_kind] = parse_values_into_dict(state.ls_values)
    return state_dict


def _get_ls_value_key(ls_value):
    """
    Key to uniquely identify a `LsThingValue`.

    :param ls_value: Ls thing value object.
    :type ls_value: LsThingValue
    :return: LsThingValue key.
    :rtype: str
    """

    key = ls_value.ls_kind
    if ls_value.unit_kind:
        key = f'{key} ({ls_value.unit_kind})'
    return key


def parse_values_into_dict(ls_values):
    """Parse a list of LsValues into a dict of { value_kind: value }
    If there are multiple non-ignored LsValues with the same type, the value in the returned dict
    will be a list of values.

    :param ls_values: List of LsValue objects
    :type ls_values: list
    :return: Dictionary of { value_kind: value } where value may be of many possible data types
    :rtype: dict
    """
    values_dict = {}
    for value in ls_values:
        if not value.ignored and not value.deleted:
            key = _get_ls_value_key(value)
            if value.ls_type == 'stringValue':
                val = value.string_value
            elif value.ls_type == 'codeValue':
                val = CodeValue(value.code_value, code_type=value.code_type,
                                code_kind=value.code_kind, code_origin=value.code_origin)
            elif value.ls_type == 'numericValue':
                val = value.numeric_value
            elif value.ls_type == 'dateValue':
                val = ts_to_datetime(value.date_value)
            elif value.ls_type == 'clobValue':
                val = clob(value.clob_value)
            elif value.ls_type == 'urlValue':
                val = value.url_value
            elif value.ls_type == 'fileValue':
                val = FileValue(ls_value=value)
            elif value.ls_type == 'blobValue':
                val = BlobValue(ls_value=value)
            # In cases where there are multiple values with same ls_kind,
            # make the dictionary value into a list and append this value
            if key in values_dict:
                if isinstance(values_dict[key], list):
                    values_dict[key].append(val)
                else:
                    value_list = [values_dict[key]]
                    value_list.append(val)
                    values_dict[key] = value_list
            else:
                values_dict[key] = val
    return values_dict


def get_lsKind_to_lsvalue(ls_values_raw):
    """Convert a list of LsValues into a dict of { value_kind: LsValue }
    If there are multiple non-ignored LsValues with the same ls_kind, the dict will have
    {value_kind: [LsValue, LsValue, ...]}

    :param ls_values_raw: List of LsValues
    :type ls_values_raw: list
    :return: dict of { value_kind: LsValue }
    :rtype: dict
    """
    # Filter out ignored values
    ls_values = [v for v in ls_values_raw if not v.ignored and not v.deleted]
    lsKind_to_lsvalue = dict()
    for ls_value in ls_values:
        key = _get_ls_value_key(ls_value)
        if key in lsKind_to_lsvalue:
            lsKind_to_lsvalue[key].append(ls_value)
        else:
            lsKind_to_lsvalue[key] = [ls_value]

    for ls_value in ls_values:
        key = _get_ls_value_key(ls_value)
        val = lsKind_to_lsvalue[key]
        if len(val) == 1:
            lsKind_to_lsvalue[key] = val[0]

    return lsKind_to_lsvalue


def is_equal_ls_value_simple_value(ls_value, val):
    """Compare an LsValue to a simple value (i.e. str, int, clob, float, etc.)
    The purpose of this function is to detect whether a given value has changed
    relative to the previously saved value and therefore needs to be updated within ACAS.

    :param ls_value: LsValue for comparison
    :type ls_value: LsValue
    :param val: simple value to compare to ls_value
    :type val: Union[list, FileValue, BlobValue, clob, str, bool, CodeValue, float, int, datetime]
    :raises ValueError: If unrecognized datatype is passed in
    :return: True if ls_value and val are equivalent, False if not
    :rtype: bool
    """
    if (isinstance(val, list) and not isinstance(ls_value, list)) \
            or (isinstance(ls_value, list) and not isinstance(val, list)):
        return False
    elif isinstance(val, FileValue):
        return FileValue(ls_value.file_value, ls_value.comments) == val
    elif isinstance(val, BlobValue):
        return BlobValue(ls_value.blob_value, ls_value.comments) == val
    elif isinstance(val, clob):
        return ls_value.clob_value == str(val)
    elif type(val) == str:
        if val.startswith('https://') or val.startswith('http://'):
            return ls_value.url_value == val
        else:
            return ls_value.string_value == val
    elif type(val) == bool:
        return ls_value.code_value == str(val)
    elif isinstance(val, CodeValue):
        return CodeValue(ls_value.code_value, ls_value.code_type, ls_value.code_kind, ls_value.code_origin) == val
    elif isinstance(val, float) or isinstance(val, int):
        return ls_value.numeric_value == val
    elif isinstance(val, datetime):
        return ts_to_datetime(ls_value.date_value) == val
    elif isinstance(val, list):
        if len(ls_value) != len(val):
            # List of values is not of same length, so cannot be equal
            return False

        ddicts = set()
        for value in ls_value:
            ddict = CodeValue(value.code_value, value.code_type,
                              value.code_kind, value.code_origin)
            ddicts.add(ddict)

        return all([value in ddicts for value in val])
    elif pd.isnull(val):
        return (pd.isnull(ls_value.code_value) and
                pd.isnull(ls_value.string_value) and
                pd.isnull(ls_value.clob_value) and
                pd.isnull(ls_value.url_value) and
                pd.isnull(ls_value.date_value) and
                pd.isnull(ls_value.file_value) and
                pd.isnull(ls_value.blob_value) and
                pd.isnull(ls_value.numeric_value)
                )
    else:
        raise ValueError(
            "Comparing values of type {} are not yet implemented!".format(type(val)))


def get_units_from_string(string):
    """Extract units from a string of format "field (units)"

    :param string: raw string to extract from
    :type string: str
    :return: Units extracted, as a str, or None
    :rtype: Union[str, None]
    """
    # Gets the units from strings,
    found_string = re.sub(r".*\((.*)\).*|(.*)", r"\1", string)
    units = None
    if found_string != "":
        units = found_string
    return units


def get_value_kind_without_extras(string):
    """Strip undesired characters and patterns from a string to prepare it to be used as an ls_kind for an LsValue

    :param string: raw string
    :type string: str
    :return: cleaned string
    :rtype: str
    """
    return re.sub(r"\[[^)]*\]", "", re.sub(r"(.*)\((.*)\)(.*)", r"\1\3", re.sub(r"\{[^}]*\}", "", string))).strip()


def _upload_file_value(file_value, client):
    """Upload a single FileValue to the ACAS server and return an updated FileValue
    containing the on-server file path.

    :param file_value: FileValue to be uploaded
    :type file_value: FileValue
    :param client: Authenticated acasclient.client
    :type client: acasclient.client
    :return: Updated FileValue
    :rtype: FileValue
    """
    val = pathlib.Path(file_value.value)
    uploaded_files = client.upload_files([val])
    uploaded_file = uploaded_files['files'][0]
    return FileValue(
        value=uploaded_file['name'],
        comments=uploaded_file["originalName"])


def make_ls_value(value_cls, value_kind, val, recorded_by):
    """Construct an LsValue of class `value_cls` that can be recognized and persisted by ACAS

    :param value_cls: class of desired output. Should inherit from AbstractValue
    :type value_cls: class inherited from AbstractValue
    :param value_kind: ls_kind of LsValue
    :type value_kind: str
    :param val: Raw value to be represented by the LsValue
    :type val: Union[list, FileValue, BlobValue, clob, str, bool, CodeValue, float, int, datetime]
    :param recorded_by: Username to associate with the value for auditing purposes
    :type recorded_by: str
    :raises ValueError: If val of unrecognized datatype is passed in
    :return: LsValue of class `value_cls`
    :rtype: determined by `value_cls` argument
    """
    unit_kind = get_units_from_string(value_kind)
    value_kind = get_value_kind_without_extras(value_kind)
    if isinstance(val, FileValue):
        value = value_cls(ls_type="fileValue", ls_kind=value_kind, recorded_by=recorded_by,
                          file_value=val.value, comments=val.comments, unit_kind=unit_kind)
    elif isinstance(val, BlobValue):
        value = value_cls(
            ls_type="blobValue",
            ls_kind=value_kind,
            recorded_by=recorded_by,
            blob_value=val.value,
            unit_kind=unit_kind,
            comments=val.comments,
        )
    elif isinstance(val, str) and val not in ['true', 'false']:
        if len(val) > 255 or isinstance(val, clob):
            value = value_cls(ls_type='clobValue', ls_kind=value_kind, recorded_by=recorded_by,
                              clob_value=val, unit_kind=unit_kind)
        elif val.startswith('https://') or val.startswith('http://'):
            value = value_cls(ls_type='urlValue', ls_kind=value_kind, recorded_by=recorded_by,
                              url_value=val, unit_kind=unit_kind)
        else:
            value = value_cls(ls_type='stringValue', ls_kind=value_kind, recorded_by=recorded_by,
                              string_value=val, unit_kind=unit_kind)
    elif type(val) == bool or (isinstance(val, str) and val in ['true', 'false']):
        value = value_cls(ls_type='codeValue', ls_kind=value_kind, recorded_by=recorded_by,
                          code_value=str(val).lower(), unit_kind=unit_kind)
    elif isinstance(val, CodeValue):
        value = value_cls(ls_type='codeValue', ls_kind=value_kind, recorded_by=recorded_by,
                          code_value=val.code, code_type=val.code_type, code_kind=val.code_kind, code_origin=val.code_origin, unit_kind=unit_kind)
    elif isinstance(val, float) or isinstance(val, int):
        if pd.isnull(val):
            val = None
        value = value_cls(ls_type='numericValue', ls_kind=value_kind, recorded_by=recorded_by,
                          numeric_value=val, unit_kind=unit_kind)
    elif isinstance(val, datetime):
        value = value_cls(ls_type='dateValue', ls_kind=value_kind, recorded_by=recorded_by,
                          date_value=datetime_to_ts(val), unit_kind=unit_kind)
    else:
        raise ValueError(
            "Saving values of type {} are not yet implemented!".format(type(val)))
    return value


def update_ls_states_from_dict(state_class, state_type, value_class, state_value_simple_dict, ls_states_dict, ls_values_dict, edit_user, client, upload_files):
    """Translates updates between the "simple dict" data model and the more complex LsState / LsValue data model.
    If a new state is needed, this method will create a new LsState. Otherwise it will update existing LsStates in place.
    This method includes a nested update of all underlying LsValues as well.

    :param state_class: class of LsState being handled. Used when creating new LsStates
    :type state_class: subclass of AbstractState
    :param state_type: lsType of LsStates
    :type state_type: str
    :param value_class: class of LsValue being handled. Used by nested function when creating new LsValues
    :type value_class: subclass of AbstractValue
    :param state_value_simple_dict: Simple dict of format { state_kind: { value_kind: value } }
    :type state_value_simple_dict: dict
    :param ls_states_dict: dict of LsState objects with format {state_kind: LsState}
    :type ls_states_dict: dict
    :param ls_values_dict: dict of LsValue objects with format {state_kind: {value_kind: LsValue}}
    :type ls_values_dict: dict
    :param edit_user: Username to be associated with changes, for auditing purposes
    :type edit_user: str
    :param client: Authenticated acasclient.client instance
    :type client: acasclient.client
    :param upload_files: Whether to upload new FileValues, defaults to True
    :type upload_files: bool
    :return: list of LsStates with updates applied
    :rtype: list
    """
    ls_states = []
    for state_kind, values_dict in state_value_simple_dict.items():
        try:
            state = ls_states_dict[state_kind]
        except KeyError:
            # state not found, so create one
            state = state_class(ls_type=state_type,
                                ls_kind=state_kind, recorded_by=edit_user)
        try:
            current_values = ls_values_dict[state_kind]
        except KeyError:
            current_values = {}
        ls_values = update_ls_values_from_dict(
            value_class, values_dict, current_values, edit_user, client, upload_files)
        state.ls_values = ls_values
        ls_states.append(state)
    return ls_states


def update_state_table_states_from_dict(state_class, value_class, state_table_simple_dict, state_table_states, state_table_values, edit_user, client, upload_files):
    """Translates updates between the "state table simple dict" data model and the more complex LsState model.
    If a new state is needed, this method will create a new LsState. Otherwise it will update existing LsStates in place.
    This method includes a nested update of all underlying LsValues as well.

    State Tables in ACAS are used when there are multiple LsStates with identical lsType and lsKind on the same Thing. These different
    states are differentiated by a `row number` value that allows them to be rendered in a tabular format.

    :param state_class: class of LsState being handled. Used when creating new LsStates
    :type state_class: subclass of AbstractState
    :param value_class: class of LsValue being handled. Used by nested function when creating new LsValues
    :type value_class: subclass of AbstractValue
    :param state_table_simple_dict: Simpler dict of format { (state_type, state_kind): row_number: {value_kind: value}}
    :type state_table_simple_dict: dict
    :param state_table_states: Dict of format { (state_type, state_kind): row_number: LsState }
    :type state_table_states: dict
    :param state_table_values: Dict of format { (state_type, state_kind): row_number: {value_kind: LsValue}}
    :type state_table_values: dict
    :param edit_user: Username to be associated with changes, for auditing purposes
    :type edit_user: str
    :param client: Authenticated acasclient.client instance
    :type client: acasclient.client
    :param upload_files: Whether to upload new FileValues, defaults to True
    :type upload_files: bool
    :return: list of LsStates with updates applied
    :rtype: list
    """
    ls_states = []
    for type_kind_key, state_table in state_table_simple_dict.items():
        for row_num, values_dict in state_table.items():
            try:
                state = state_table_states[type_kind_key][row_num]
            except KeyError:
                # state not found, so create one
                state_type, state_kind = type_kind_key
                state = state_class(ls_type=state_type,
                                    ls_kind=state_kind, recorded_by=edit_user)
            # Ensure there is a row number value, and if not auto-create it
            if ROW_NUM_KEY not in values_dict:
                values_dict[ROW_NUM_KEY] = row_num
            try:
                current_values = state_table_values[type_kind_key][row_num]
            except KeyError:
                current_values = {}
            ls_values = update_ls_values_from_dict(
                value_class, values_dict, current_values, edit_user, client, upload_files)
            state.ls_values = ls_values
            ls_states.append(state)
    return ls_states


def update_ls_values_from_dict(value_class, simple_value_dict, ls_values_dict, edit_user, client, upload_files):
    """Translates updates from the "simple dict" data model into the more complex LsValue data model

    :param value_class: class of LsValue being handled. Used when creating new LsValues
    :type value_class: subclass of AbstractValue
    :param simple_value_dict: dict of format {value_kind: value}
    :type simple_value_dict: dict
    :param ls_values_dict: dict of format {value_kind: LsValue}
    :type ls_values_dict: dict
    :param edit_user: Username to be associated with changes, for auditing purposes
    :type edit_user: str
    :param client: Authenticated acasclient.client instance
    :type client: acasclient.client
    :param upload_files: Whether to upload new FileValues, defaults to True
    :type upload_files: bool
    :return: list of LsValues with updates applied
    :rtype: list
    """
    ls_values = []
    for val_kind, val_value in simple_value_dict.items():
        new_val_is_list = isinstance(val_value, list)
        if val_kind in ls_values_dict:
            old_ls_val = ls_values_dict[val_kind]
            old_val_is_list = isinstance(old_ls_val, list)
            # old_val_value = old_ls_val.clob_value or old_ls_val.string_value or old_ls_val.numeric_value or old_ls_val.date_value or old_ls_val.code_value
            if not is_equal_ls_value_simple_value(old_ls_val, val_value):
                # Value is "dirty" so we need to prepare to persist an update
                # in ACAS, we mark the old LsValue as ignored, then create a new LsValue
                if new_val_is_list:
                    new_val_null = pd.isnull(val_value).all()
                else:
                    new_val_null = pd.isnull(val_value)
                if not new_val_null:
                    # If enabled, check if new value is a FileValue and needs to first be uploaded to ACAS
                    if upload_files and isinstance(val_value, FileValue) and val_value.value:
                        val_value = _upload_file_value(val_value, client)
                        simple_value_dict[val_kind] = val_value
                    # Handle lists within the value dict
                    if new_val_is_list:
                        new_ls_vals = [make_ls_value(
                            value_class, val_kind, val, edit_user) for val in val_value]
                        ls_values.extend(new_ls_vals)
                    else:
                        new_ls_val = make_ls_value(
                            value_class, val_kind, val_value, edit_user)
                        ls_values.append(new_ls_val)
                # To handle lists we cast old_ls_val into a list at this point if it's not
                if old_val_is_list:
                    for olv in old_ls_val:
                        olv.ignored = True
                        olv.modified_by = edit_user
                        olv.modified_date = datetime_to_ts(datetime.now())
                else:
                    old_ls_val.ignored = True
                    old_ls_val.modified_by = edit_user
                    old_ls_val.modified_date = datetime_to_ts(datetime.now())
            if old_val_is_list:
                ls_values.extend(old_ls_val)
            else:
                ls_values.append(old_ls_val)
        else:
            if val_value is not None:
                # If enabled, check if new value is a FileValue and needs to first be uploaded to ACAS
                if upload_files and isinstance(val_value, FileValue) and val_value.value:
                    val_value = _upload_file_value(val_value, client)
                    simple_value_dict[val_kind] = val_value
                # New value of an ls_kind not seen before
                # Handle lists within the value dict
                if new_val_is_list:
                    new_ls_vals = [make_ls_value(
                        value_class, val_kind, val, edit_user) for val in val_value]
                    ls_values.extend(new_ls_vals)
                else:
                    new_ls_val = make_ls_value(
                        value_class, val_kind, val_value, edit_user)
                    ls_values.append(new_ls_val)
    return ls_values


def update_ls_labels_from_dict(label_class, label_type, simple_label_dict, ls_labels_dict, edit_user, preferred_label_kind=None):
    """Translates the "simple dict" data model into the more complex ACAS LsLabel format.

    :param label_class: class of LsLabel being handled. Used when creating a new LsLabel.
    :type label_class: subclass of AbstractLabel
    :param label_type: lsType of LsLabels to create
    :type label_type: str
    :param simple_label_dict: dict of format {label_kind: value}
    :type simple_label_dict: dict
    :param ls_labels_dict: dict of format {label_kind: LsLabel}
    :type ls_labels_dict: dict
    :param edit_user: Username to associate with changes, for auditing purposes
    :type edit_user: str
    :param preferred_label_kind: lsKind of LsLabel that is "preferred" for this LsThing, defaults to None.
                                 New labels created that have this ls_kind will be marked with `preferred=True`
    :type preferred_label_kind: str, optional
    :return: list of LsLabels with updates applied
    :rtype: list
    """
    ls_labels = []
    for label_kind, label_text in simple_label_dict.items():
        if isinstance(label_text, list):
            # Multiple labels with same kind, i.e. aliases
            label_list = label_text
            replace_all = (len(label_list) > 0)
            old_ls_labels = ls_labels_dict[label_kind]
            for old_ls_label in old_ls_labels:
                if replace_all:
                    # If provided a non-empty new list, expected behavior is to clear out all existing labels and replace with the new set
                    old_ls_label.ignored = True
                    old_ls_label.modified_by = edit_user,
                    old_ls_label.modified_date = datetime_to_ts(datetime.now())
                ls_labels.append(old_ls_label)
            # Replace with the new set
            if replace_all:
                for new_label_text in label_list:
                    preferred = False  # preferred is not allowed for aliases
                    new_ls_label = label_class(ls_type=label_type, ls_kind=label_kind,
                                               label_text=new_label_text, preferred=preferred, recorded_by=edit_user)
                    ls_labels.append(new_ls_label)
        else:
            if label_kind in ls_labels_dict:
                old_ls_label = ls_labels_dict[label_kind]
                if old_ls_label.label_text != label_text:
                    # Label has changed. Mark old LsLabel as ignored and create  a new LsLabel
                    if label_text is not None:
                        preferred = (label_kind == preferred_label_kind)
                        new_ls_label = label_class(
                            ls_type=label_type, ls_kind=label_kind, label_text=label_text, preferred=preferred, recorded_by=edit_user)
                        ls_labels.append(new_ls_label)
                    old_ls_label.ignored = True
                    old_ls_label.modified_by = edit_user
                    old_ls_label.modified_date = datetime_to_ts(datetime.now())
                ls_labels.append(old_ls_label)
            else:
                if label_text is not None:
                    # New label of an ls_kind not seen before
                    preferred = (label_kind == preferred_label_kind)
                    new_ls_label = label_class(ls_type=label_type, ls_kind=label_kind,
                                               label_text=label_text, preferred=preferred, recorded_by=edit_user)
                    ls_labels.append(new_ls_label)
    return ls_labels


class clob(str):
    """Class used to represent long string values (> 255 chars) in ACAS, saved to a database field of type `text`.
    Used as a wrapper around str, and can be used to force ACAS to save shorter values as clobValue type for consistency
    if the desired datatype is clobValue.

    :param str: long string
    :type str: str
    """
    pass


class FileValue(object):
    """Class used to save files to ACAS. ACAS has a folder of uploaded files on the filesystem, and stores references
    to the file paths as LsValues with ls_type='fileValue', file_value=filepath
    """
    _fields = ['value', 'comments']

    def __init__(self, value=None, comments=None, ls_value=None, file_path=None):
        if ls_value is not None:
            value = ls_value.file_value
            comments = ls_value.comments
        if file_path is not None:
            if isinstance(file_path, Path) or isinstance(file_path, str):
                if isinstance(file_path, str):
                    file_path = Path(file_path)
                if comments is None:
                    comments = file_path.name
                if not file_path.exists():
                    raise ValueError('File path "{}" does not exist'.format(file_path))
                if not file_path.is_file():
                    raise ValueError('File path "{}" is not a file'.format(file_path))
                value = str(file_path)
            else:
                raise ValueError('file_path must be of str or <pathlib.PosixPath>. Provided file_path argument is of type {}'.format(type(value)))
        self.value = value
        self.comments = comments

    def __eq__(self, other: object) -> bool:
        if other is None:
            return False
        return self.value == other.value and self.comments == other.comments

    def download_to_disk(self, client, folder_path='./'):
        """Download file from ACAS and save to disk

        :param client: a valid acas client
        :type client: <acasclient.lsthing.LsThingValue>
        :param folder_path: local directory path to write file into
        :type folder_path: Union[str, <pathlib.PosixPath>], optional
        :return: local filepath to written file
        :rtype: str
        """
        if isinstance(folder_path, str):
            folder_path = Path(folder_path)
        if not folder_path.exists():
            raise ValueError('folder_path path "{}" does not exist'.format(folder_path))
        acas_file = client.get_file(f'/dataFiles/{self.value}')
        if self.comments:
            acas_file["name"] = self.comments
        return str(client.write_file(acas_file, folder_path))

    def as_dict(self) -> Dict[str, Any]:
        """
        Return a map of attribute name and attribute values stored on the
        instance.
        Note: Only attributes stored in `FileValue._fields` will be returned.
        """
        return {
            field: getattr(self, field, None)
            for field in self._fields
        }


class BlobValue(object):
    """Class used to save files as byte arrays to ACAS.
    These files must be small (< 1 GB) and will be stored in a `bytea` database column.
    """
    _fields = ['value', 'comments', 'id']

    def __init__(self, value=None, comments=None, file_path=None, id=None, ls_value=None):
        """Create a BlobValue

        :param value: Bytes of file content, defaults to None
        :type value: bytes, optional
        :param comments: Filename as a string, defaults to None
        :type comments: str, optional
        :param id: id as an int, defaults to None
        :type id: int, optional
        :param file_path: file_path as an str or <pathlib.PosixPath>, defaults to None
        :type file_path: Union[str, <pathlib.PosixPath>], optional
        :param ls_value: ls_value as a <acasclient.lsthing.LsThingValue>, defaults to None
        :type ls_value: <acasclient.lsthing.LsThingValue>, optional
        """
        if ls_value is not None:
            value = ls_value.blob_value
            comments = ls_value.comments
            id = ls_value.id
        else:
            if file_path is not None:
                if isinstance(file_path, Path) or isinstance(file_path, str):
                    if isinstance(file_path, str):
                        file_path = Path(file_path)
                    if comments is None:
                        comments = file_path.name
                    if not file_path.exists():
                        raise ValueError('File path "{}" does not exist'.format(file_path))
                    if not file_path.is_file():
                        raise ValueError('File path "{}" is not a file'.format(file_path))
                    f = file_path.open('rb')
                    bytes_array = f.read()
                    value = [x for x in bytes_array]
                    f.close()
                else:
                    raise ValueError('file_path must be of str or <pathlib.PosixPath>. Provided file_path argument is of type {}'.format(type(file_path)))
        self.value = value
        self.comments = comments
        self.id = id

    def download_data(self, client):
        """Get blob value data as bytes

        :param client: a valid acas client
        :type client: <acasclient.lsthing.LsThingValue>
        :return: bytes of blob value from server
        :rtype: bytes
        """
        if self.id is None:
            raise ValueError('Cannot download data because BlobValue does not have id. Check to see if it has been saved.')
        self.value = client.get_blob_data_by_value_id(self.id)
        return self.value

    def write_to_file(self, folder_path=None, file_name=None, full_file_path=None):
        """Write blob value to a file (requires that BlobValue.value has valid bytes).
           This can be achieved but running <acasclient.lsthing.BlobValue.download_data> on the BlobValue

        :param folder_path: folder_path as an str or <pathlib.PosixPath>, defaults to None
        :type folder_path: Union[str, <pathlib.PosixPath>], optional
        :param file_name: file_name as an str or <pathlib.PosixPath>, defaults to value.comments or full_file_path name if passed in
        :type file_name: Union[str, <pathlib.PosixPath>], optional
        :param full_file_path: full_file_path as an str or <pathlib.PosixPath>, defaults to None
        :type full_file_path: Union[str, <pathlib.PosixPath>], optional
        :return: <pathlib.PosixPath> of written data file
        :rtype: <pathlib.PosixPath>
        """
        if self.value is None:
            raise ValueError('Error writing file. BlobValue does not have a value set.')
        if full_file_path is not None:
            if not isinstance(full_file_path, Path) and not isinstance(full_file_path, str):
                raise ValueError('full_file_path must be of str or <pathlib.PosixPath>. Provided full_file_path argument is of type {}'.format(type(full_file_path)))
            if isinstance(full_file_path, str):
                full_file_path = Path(full_file_path)
            if not full_file_path.parents[0].exists():
                raise ValueError('Parent directory of full_file_path path "{}" does not exist'.format(full_file_path.parents[0]))
            if full_file_path.exists() and not full_file_path.is_file():
                raise ValueError('File path "{}" exists and is not a file.  File path should be a file'.format(full_file_path))
        else:
            if folder_path is None:
                raise ValueError('folder_path argument must be provided if full_file_path is not provided')
            if not isinstance(folder_path, Path) and not isinstance(folder_path, str):
                raise ValueError('folder_path must be of str or <pathlib.PosixPath>. Provided folder_path argument is of type {}'.format(type(folder_path)))
            if isinstance(folder_path, str):
                folder_path = Path(folder_path)
            if not folder_path.exists():
                raise ValueError('folder_path path "{}" does not exist'.format(folder_path))
            if file_name is None and self.comments is None:
                raise ValueError('file_name argument must be provided if BlobValue comments is None')
            else:
                if file_name is None:
                    file_name = self.comments
            full_file_path = Path(folder_path, file_name)
        with open(full_file_path, 'wb') as f:
            f.write(self.value)
        return full_file_path

    def __eq__(self, other: object) -> bool:
        if other is None:
            return False
        return self.value == other.value and self.comments == other.comments

    def as_dict(self) -> Dict[str, Any]:
        """
        Return a map of attribute name and attribute values stored on the
        instance.
        Note: Only attributes stored in `BlobValue._fields` will be returned.
        """
        return {
            field: getattr(self, field, None)
            for field in self._fields
        }


# Model classes

class BaseModel(object):
    """Base class for attributes shared by all levels of ACAS objects (thing, label, state, value)
    """
    _fields = ['id', 'ls_type', 'ls_kind', 'deleted', 'ignored', 'version']

    def __init__(self, id=None, ls_type=None, ls_kind=None, deleted=False, ignored=False, version=None):
        self.id = id
        self.ls_type = ls_type
        self.ls_kind = ls_kind
        self.deleted = deleted
        self.ignored = ignored
        self.version = version

    def as_dict(self):
        """Serialize instance as a dict

        :return: dictionary of instance attributes specified in `self._fields`
        :rtype: dict
        """
        data = {}
        for field in self._fields:
            method = 'serialize_{0}'.format(field)
            if hasattr(self, method):
                value = getattr(self, method)()
            else:
                value = getattr(self, field)

            data[field] = value

        return data

    def as_camel_dict(self):
        """Serialize instance as a dict with camelCase keys

        :return: dict of instance attributes specified in `self._fields` but with camelCase keys
        :rtype: dict
        """
        snake_case_dict = self.as_dict()
        camel_dict = convert_json(snake_case_dict, underscore_to_camel)
        return camel_dict

    def as_json(self, **kwargs):
        """Serialize instance into a JSON string with camelCase keys

        :return: JSON string containing attributes specified in `self._fields` but with camelCase keys
        :rtype: str
        """
        camel_dict = self.as_camel_dict()
        return json.dumps(camel_dict, **kwargs)

    @classmethod
    def as_list(cls, models):
        """Convert a list of objects into a list of dicts

        :param models: list of AbstractModel objects
        :type models: list
        :return: list of dicts
        :rtype: list
        """
        return [model.as_dict() for model in models or []]

    @classmethod
    def as_json_list(cls, models):
        """Convert a list of objects into a JSON string list of dicts

        :param models: list of AbstractModel objets
        :type models: list
        :return: JSON string representing list of dicts
        :rtype: str
        """
        return json.dumps([json.loads(model.as_json()) for model in models or []])

    @classmethod
    def from_camel_dict(cls, data):
        """Construct an AbstractModel object from a camelCase dict

        :param data: dict of attributes
        :type data: dict
        :return: instance of class AbstractModel
        :rtype: AbstractModel
        """
        snake_case_dict = convert_json(data, camel_to_underscore)
        return cls.from_dict(snake_case_dict)

    @classmethod
    def from_dict(cls, data):
        """Construct an AbstractModel object from a dict

        :param data: dict with attributes matching cls._fields
        :type data: dict
        :return: AbstractModel object
        :rtype: AbstractModel
        """
        local_data = {}
        for field in cls._fields:
            if field in data:
                field_data = copy.deepcopy(data[field])
                method = 'deserialize_{0}'.format(field)
                if hasattr(cls, method):
                    local_data[field] = getattr(cls, method)(field_data)
                else:
                    local_data[field] = field_data
        return cls(**local_data)

    @classmethod
    def from_json(cls, data):
        """Construct an AbstractModel object from a JSON string with camelCase attribute keys

        :param data: JSON string from ACAS with camelCase attribute keys
        :type data: str
        :return: AbstractModel object
        :rtype: AbstractModel
        """
        camel_dict = json.loads(data)
        snake_case_dict = convert_json(camel_dict, camel_to_underscore)
        return cls.from_dict(json.loads(snake_case_dict))

    @classmethod
    def from_list(cls, arr):
        """Convert a list of dicts into a list of AbstractModel objects

        :param arr: list of dicts
        :type arr: list
        :return: list of AbstractModel objects
        :rtype: list
        """
        return [cls.from_dict(elem) for elem in arr]


class CodeValue(object):
    """ ACAS uses the "codeValue" type to save data that referencess a controlled dictionary of possible values.

    In ACAS, these controlled vocabularies are called DDictValues, short for Data Dictionary Values.
    DDictValues are grouped together by "code_type" and "code_kind", then the individual possible values are specified by the "code" attribute.

    The CodeValue class is used to save references to DDictValues as LsValues of ls_type='codeValue'.
    """
    _fields = ['code_type', 'code_kind', 'code_origin', 'code']

    def __init__(self, code, code_type=None, code_kind=None,
                 code_origin=None, client=None):
        error_msg = self._validate_params(code, code_type, code_kind,
                                          code_origin, client)
        if error_msg is not None:
            raise ValueError(error_msg)

        self.code = code
        self.code_type = code_type
        self.code_kind = code_kind
        self.code_origin = code_origin

    def __hash__(self):
        return hash(f'{self.code}-{self.code_type}-{self.code_kind}-'
                    f'{self.code_origin}')

    def _validate_params(self, code, code_type, code_kind, code_origin, client):
        """Validate that this CodeValue conforms to the saved list of possible DDictValues

        :param code: value of this CodeValue, i.e. which DDictValue is being referenced
        :type code: str
        :param code_type: LsType of DDictValue being referenced
        :type code_type: str
        :param code_kind: LsKind of DDictValue being referenced
        :type code_kind: str
        :param code_origin: Origin of DDictValue referenced, typically 'ACAS DDict'
        :type code_origin: str
        :param client: Authenticated acasclient.client instance to look up current DDictValues
        :type client: acasclient.client
        :return: Error message, or None if valid
        :rtype: str | None
        """
        if client is None:
            return
        valid_val_dicts = client.get_ddict_values_by_type_and_kind(
            code_type, code_kind)
        if valid_val_dicts == []:
            return (f"Invalid 'code_type':'{code_type}' or "
                    f"'code_kind':'{code_kind}' provided")
        if any([code == val_dict['code'] for val_dict in valid_val_dicts]):
            return

        return (f"Invalid 'code':'{code}' provided for the given "
                f"'code_type':'{code_type}' and 'code_kind':'{code_kind}'")

    def as_dict(self):
        return self.__dict__

    def __eq__(self, value):
        return all([
            self.code == value.code,
            self.code_type == value.code_type,
            self.code_kind == value.code_kind,
            self.code_origin == value.code_origin
        ])

# Base ACAS entities, states, values, and interactions


class AbstractThing(BaseModel):
    """Base class for LsThing and ItxLsThingLsThing ACAS objects
    """

    _fields = BaseModel._fields + ['code_name', 'ls_transaction',
                                   'modified_by', 'modified_date', 'recorded_by', 'recorded_date']

    def __init__(self,
                 id=None,
                 code_name=None,
                 deleted=False,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 modified_by=None,
                 modified_date=None,
                 recorded_by=None,  # Should this and recorded_date be auto-filled-in here?
                 recorded_date=None,
                 version=None):
        super(AbstractThing, self).__init__(id=id, deleted=deleted,
                                            ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
        self.code_name = code_name
        self.ls_transaction = ls_transaction
        self.modified_by = modified_by
        self.modified_date = modified_date
        self.recorded_by = recorded_by
        self.recorded_date = datetime_to_ts(
            datetime.now()) if recorded_date is None else recorded_date


class AbstractLabel(BaseModel):
    """Base class for ACAS LsLabel objects such as LsThingLabel and ItxLsThingLsThingLabel
    """

    _fields = BaseModel._fields + ['image_file', 'label_text', 'ls_transaction', 'modified_date', 'physically_labled',
                                   'preferred', 'recorded_by', 'recorded_date', 'version']

    def __init__(self,
                 id=None,
                 deleted=False,
                 ignored=False,
                 image_file=None,
                 label_text=None,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 modified_date=None,
                 physically_labled=False,
                 preferred=False,
                 recorded_by=None,  # Should this and recorded_date be auto-filled-in here?
                 recorded_date=None,
                 version=None):
        super(AbstractLabel, self).__init__(id=id, deleted=deleted,
                                            ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
        self.image_file = image_file
        if len(label_text) > 255:
            raise ValueError('Label text "{}" exceeds max length of 255 characters. It is {} characters'.format(
                label_text, len(label_text)))
        self.label_text = label_text
        self.ls_transaction = ls_transaction
        self.modified_date = modified_date
        self.physically_labled = physically_labled
        self.preferred = preferred
        self.recorded_by = recorded_by
        self.recorded_date = datetime_to_ts(
            datetime.now()) if recorded_date is None else recorded_date


class AbstractState(BaseModel):
    """Base class for ACAS LsState objects
    """

    _fields = BaseModel._fields + ['comments', 'ls_transaction',
                                   'modified_by', 'modified_date', 'recorded_by', 'recorded_date']

    def __init__(self,
                 id=None,
                 comments=None,
                 deleted=False,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 modified_by=None,
                 modified_date=None,
                 recorded_by=None,  # Should this and recorded_date be auto-filled-in here?
                 recorded_date=None,
                 version=None):
        super(AbstractState, self).__init__(id=id, deleted=deleted,
                                            ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
        self.comments = comments
        self.ls_transaction = ls_transaction
        self.modified_by = modified_by
        self.modified_date = modified_date
        self.recorded_by = recorded_by
        self.recorded_date = datetime_to_ts(
            datetime.now()) if recorded_date is None else recorded_date


class AbstractValue(BaseModel):
    """Base class for ACAS LsValue objects
    """

    _fields = BaseModel._fields + ['blob_value', 'clob_value', 'code_kind', 'code_origin', 'code_type', 'code_value', 'comments',
                                   'conc_unit', 'concentration', 'date_value', 'file_value', 'ls_transaction', 'modified_by',
                                   'modified_date', 'number_of_replicates', 'numeric_value', 'operator_kind', 'operator_type',
                                   'public_data', 'recorded_by', 'recorded_date', 'sig_figs', 'string_value', 'uncertainty',
                                   'uncertainty_type', 'unit_kind', 'unit_type', 'url_value']

    def __init__(self,
                 id=None,
                 blob_value=None,
                 clob_value=None,
                 code_kind=None,
                 code_origin=None,
                 code_type=None,
                 code_value=None,
                 comments=None,
                 conc_unit=None,
                 concentration=None,
                 date_value=None,
                 deleted=False,
                 file_value=None,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 modified_by=None,
                 modified_date=None,
                 number_of_replicates=None,
                 numeric_value=None,
                 operator_kind=None,
                 operator_type=None,
                 public_data=True,
                 recorded_by=None,  # Should this and recorded_date be auto-filled-in here?
                 recorded_date=None,
                 sig_figs=None,
                 string_value=None,
                 uncertainty=None,
                 uncertainty_type=None,
                 unit_kind=None,
                 unit_type=None,
                 url_value=None,
                 version=None):
        super(AbstractValue, self).__init__(id=id, deleted=deleted,
                                            ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
        self.blob_value = blob_value
        self.clob_value = clob_value
        self.code_kind = code_kind
        self.code_origin = code_origin
        self.code_type = code_type
        self.code_value = code_value
        self.comments = comments
        self.conc_unit = conc_unit
        self.concentration = concentration
        self.date_value = date_value
        self.file_value = file_value
        self.ls_transaction = ls_transaction
        self.modified_by = modified_by
        self.modified_date = modified_date
        self.number_of_replicates = number_of_replicates
        self.numeric_value = numeric_value
        self.operator_kind = operator_kind
        self.operator_type = operator_type
        self.public_data = public_data
        self.recorded_by = recorded_by
        self.recorded_date = datetime_to_ts(
            datetime.now()) if recorded_date is None else recorded_date
        self.sig_figs = sig_figs
        self.string_value = string_value
        self.uncertainty = uncertainty
        self.uncertainty_type = uncertainty_type
        self.unit_kind = unit_kind
        self.unit_type = unit_type
        self.url_value = url_value


class LsThing(AbstractThing):
    """Class for creating and interacting with ACAS LsThing objects.
    This is a 1:1 mapping of the ACAS LsThing class, just with pythonic snake_case attribute names
    """

    _fields = AbstractThing._fields + \
        ['ls_states', 'ls_labels', 'first_ls_things', 'second_ls_things']

    def __init__(self,
                 id=None,
                 code_name=None,
                 deleted=False,
                 first_ls_things=None,
                 ignored=False,
                 ls_labels=None,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 ls_states=None,
                 modified_by=None,
                 modified_date=None,
                 recorded_by=None,
                 recorded_date=None,
                 second_ls_things=None,
                 version=None):
        super(LsThing, self).__init__(id=id, code_name=code_name, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                                      ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date,
                                      recorded_by=recorded_by, recorded_date=recorded_date, version=version)
        self.ls_states = ls_states or []
        self.ls_labels = ls_labels or []
        self.first_ls_things = first_ls_things or []
        self.second_ls_things = second_ls_things or []

    def get_preferred_label(self):
        """Get the first non-ignored LsThingLabel with `preferred=True`

        :return: The preferred LsThingLabel
        :rtype: LsThingLabel
        """
        for label in self.ls_labels:
            if not label.ignored and not label.deleted and label.preferred:
                return label

    def as_dict(self):
        """Serialize LsThing to python dictionary.
        This includes serializing nested objects: LsLabels, LsStates, LsValues, and ItxLsThingLsThings (interactions)

        :return: nested object as dictionary
        :rtype: dict
        """
        my_dict = super(LsThing, self).as_dict()
        state_dicts = []
        for state in self.ls_states:
            state_dicts.append(state.as_dict())
        my_dict['ls_states'] = state_dicts
        label_dicts = []
        for label in self.ls_labels:
            label_dicts.append(label.as_dict())
        my_dict['ls_labels'] = label_dicts
        first_itx_dicts = []
        for itx in self.first_ls_things:
            first_itx_dicts.append(itx.as_dict())
        my_dict['first_ls_things'] = first_itx_dicts
        second_itx_dicts = []
        for itx in self.second_ls_things:
            second_itx_dicts.append(itx.as_dict())
        my_dict['second_ls_things'] = second_itx_dicts
        return my_dict

    @classmethod
    def from_dict(cls, data):
        """Deserialize LsThing object from python dict format.
        This includes deserializing nested objects such as LsLabels, LsStates, LsValues and interactions

        :param data: dict-formatted LsThing
        :type data: dict
        :return: LsThing object
        :rtype: LsThing
        """
        my_obj = super(LsThing, cls).from_dict(data)
        ls_states = []
        for state_dict in my_obj.ls_states:
            state_obj = LsThingState.from_dict(state_dict)
            ls_states.append(state_obj)
        my_obj.ls_states = ls_states
        ls_labels = []
        for label_dict in my_obj.ls_labels:
            label_obj = LsThingLabel.from_dict(label_dict)
            ls_labels.append(label_obj)
        my_obj.ls_labels = ls_labels
        first_itxs = []
        for itx_dict in my_obj.first_ls_things:
            itx_obj = ItxLsThingLsThing.from_dict(itx_dict)
            first_itxs.append(itx_obj)
        my_obj.first_ls_things = first_itxs
        second_itxs = []
        for itx_dict in my_obj.second_ls_things:
            itx_obj = ItxLsThingLsThing.from_dict(itx_dict)
            second_itxs.append(itx_obj)
        my_obj.second_ls_things = second_itxs
        return my_obj

    def save(self, client):
        """Persist this LsThing to an ACAS server's database

        :param client: Authenticated instance of acasclient.client
        :type client: acasclient.client
        :return: Updated persisted LsThing object returned from the server
        :rtype: LsThing
        """
        if self.id and self.code_name:
            resp_dict = client.update_ls_thing_list([self.as_camel_dict()])
        else:
            resp_dict = client.save_ls_thing_list([self.as_camel_dict()])
        return LsThing.from_camel_dict(resp_dict[0])


class LsThingLabel(AbstractLabel):
    """Class to create and interact with ACAS LsThingLabels
    """

    _fields = AbstractLabel._fields + ['ls_thing']

    def __init__(self,
                 id=None,
                 deleted=False,
                 ignored=False,
                 image_file=None,
                 label_text=None,
                 ls_type=None,
                 ls_kind=None,
                 ls_thing=None,
                 ls_transaction=None,
                 modified_date=None,
                 physically_labled=False,
                 preferred=False,
                 recorded_by=None,  # Should this and recorded_date be auto-filled-in here?
                 recorded_date=None,
                 version=None):
        super(LsThingLabel, self).__init__(id=id, deleted=deleted, image_file=image_file, ignored=ignored, label_text=label_text, ls_type=ls_type,
                                           ls_kind=ls_kind, ls_transaction=ls_transaction, modified_date=modified_date, physically_labled=physically_labled,
                                           preferred=preferred, recorded_by=recorded_by, recorded_date=recorded_date, version=version)
        self.ls_thing = ls_thing


class LsThingState(AbstractState):
    """Class to create and interact with ACAS LsThingStates
    """

    _fields = AbstractState._fields + ['ls_values', 'ls_thing']

    def __init__(self,
                 id=None,
                 comments=None,
                 deleted=False,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 ls_values=None,
                 ls_thing=None,
                 modified_by=None,
                 modified_date=None,
                 recorded_by=None,
                 recorded_date=None,
                 version=None):
        super(LsThingState, self).__init__(id=id, comments=comments, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                                           ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date,
                                           recorded_by=recorded_by, recorded_date=recorded_date, version=None)
        self.ls_values = ls_values or []
        self.ls_thing = ls_thing

    def as_dict(self):
        my_dict = super(LsThingState, self).as_dict()
        value_dicts = []
        for value in self.ls_values:
            if isinstance(value, list):
                value_dicts.append([val.as_dict() for val in value])
            else:
                value_dicts.append(value.as_dict())
        my_dict['ls_values'] = value_dicts
        return my_dict

    @classmethod
    def from_dict(cls, data):
        my_obj = super(LsThingState, cls).from_dict(data)
        ls_values = []
        for value_dict in my_obj.ls_values:
            value_obj = LsThingValue.from_dict(value_dict)
            ls_values.append(value_obj)
        my_obj.ls_values = ls_values
        return my_obj


class LsThingValue(AbstractValue):
    """Class to interact with and save ACAS LsThingValues
    """

    _fields = AbstractValue._fields + ['ls_state']

    def __init__(self,
                 id=None,
                 blob_value=None,
                 clob_value=None,
                 code_kind=None,
                 code_origin=None,
                 code_type=None,
                 code_value=None,
                 comments=None,
                 conc_unit=None,
                 concentration=None,
                 date_value=None,
                 deleted=False,
                 file_value=None,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_state=None,
                 ls_transaction=None,
                 modified_by=None,
                 modified_date=None,
                 number_of_replicates=None,
                 numeric_value=None,
                 operator_kind=None,
                 operator_type=None,
                 public_data=True,
                 recorded_by=None,
                 recorded_date=None,
                 sig_figs=None,
                 string_value=None,
                 uncertainty=None,
                 uncertainty_type=None,
                 unit_kind=None,
                 unit_type=None,
                 url_value=None,
                 version=None):
        super(LsThingValue, self).__init__(id=id, blob_value=blob_value, clob_value=clob_value, code_kind=code_kind, code_origin=code_origin,
                                           code_type=code_type, code_value=code_value, comments=comments, conc_unit=conc_unit,
                                           concentration=concentration, date_value=date_value, deleted=deleted, file_value=file_value, ignored=ignored,
                                           ls_type=ls_type, ls_kind=ls_kind, ls_transaction=ls_transaction, modified_by=modified_by,
                                           modified_date=modified_date, number_of_replicates=number_of_replicates, numeric_value=numeric_value,
                                           operator_kind=operator_kind, operator_type=operator_type, public_data=public_data, recorded_by=recorded_by,
                                           recorded_date=recorded_date, sig_figs=sig_figs, string_value=string_value, uncertainty=uncertainty,
                                           uncertainty_type=uncertainty_type, unit_kind=unit_kind, unit_type=unit_type, url_value=url_value,
                                           version=version)
        self.ls_state = ls_state


class ItxLsThingLsThing(AbstractThing):
    """Class to manage ACAS ItxLsThingLsThings, which are rich "interactions" or links between LsThings.
    """

    _fields = AbstractThing._fields + \
        ['ls_states', 'first_ls_thing', 'second_ls_thing']

    def __init__(self,
                 id=None,
                 code_name=None,
                 deleted=False,
                 first_ls_thing=None,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 ls_states=None,
                 modified_by=None,
                 modified_date=None,
                 recorded_by=None,
                 recorded_date=None,
                 second_ls_thing=None,
                 version=None):
        super(ItxLsThingLsThing, self).__init__(id=id, code_name=code_name, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                                                ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date,
                                                recorded_by=recorded_by, recorded_date=recorded_date, version=version)
        self.ls_states = ls_states or []
        self.first_ls_thing = first_ls_thing
        self.second_ls_thing = second_ls_thing

    def as_dict(self):
        my_dict = super(ItxLsThingLsThing, self).as_dict()
        state_dicts = []
        for state in self.ls_states:
            state_dicts.append(state.as_dict())
        my_dict['ls_states'] = state_dicts
        if self.first_ls_thing:
            my_dict['first_ls_thing'] = self.first_ls_thing.as_dict()
        if self.second_ls_thing:
            my_dict['second_ls_thing'] = self.second_ls_thing.as_dict()
        return my_dict

    @classmethod
    def from_dict(cls, data):
        my_obj = super(ItxLsThingLsThing, cls).from_dict(data)
        ls_states = []
        for state_dict in my_obj.ls_states:
            state_obj = LsThingState.from_dict(state_dict)
            ls_states.append(state_obj)
        my_obj.ls_states = ls_states
        if my_obj.first_ls_thing:
            my_obj.first_ls_thing = LsThing.from_dict(my_obj.first_ls_thing)
        if my_obj.second_ls_thing:
            my_obj.second_ls_thing = LsThing.from_dict(my_obj.second_ls_thing)
        return my_obj


class ItxLsThingLsThingState(AbstractState):

    _fields = AbstractState._fields + ['ls_values', 'itx_ls_thing_ls_thing']

    def __init__(self,
                 id=None,
                 comments=None,
                 deleted=False,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_transaction=None,
                 ls_values=None,
                 itx_ls_thing_ls_thing=None,
                 modified_by=None,
                 modified_date=None,
                 recorded_by=None,
                 recorded_date=None,
                 version=None):
        super(ItxLsThingLsThingState, self).__init__(id=id, comments=comments, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                                                     ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date,
                                                     recorded_by=recorded_by, recorded_date=recorded_date, version=None)
        self.ls_values = ls_values or []
        self.itx_ls_thing_ls_thing = itx_ls_thing_ls_thing

    def as_dict(self):
        my_dict = super(ItxLsThingLsThingState, self).as_dict()
        value_dicts = []
        for value in self.ls_values:
            value_dicts.append(value.as_dict())
        my_dict['ls_values'] = value_dicts
        return my_dict

    @classmethod
    def from_dict(cls, data):
        my_obj = super(ItxLsThingLsThingState, cls).from_dict(data)
        ls_values = []
        for value_dict in my_obj.ls_values:
            value_obj = ItxLsThingLsThingValue.from_dict(value_dict)
            ls_values.append(value_obj)
        my_obj.ls_values = ls_values
        return my_obj


class ItxLsThingLsThingValue(AbstractValue):

    _fields = AbstractValue._fields + ['ls_state']

    def __init__(self,
                 id=None,
                 blob_value=None,
                 clob_value=None,
                 code_kind=None,
                 code_origin=None,
                 code_type=None,
                 code_value=None,
                 comments=None,
                 conc_unit=None,
                 concentration=None,
                 date_value=None,
                 deleted=False,
                 file_value=None,
                 ignored=False,
                 ls_type=None,
                 ls_kind=None,
                 ls_state=None,
                 ls_transaction=None,
                 modified_by=None,
                 modified_date=None,
                 number_of_replicates=None,
                 numeric_value=None,
                 operator_kind=None,
                 operator_type=None,
                 public_data=True,
                 recorded_by=None,
                 recorded_date=None,
                 sig_figs=None,
                 string_value=None,
                 uncertainty=None,
                 uncertainty_type=None,
                 unit_kind=None,
                 unit_type=None,
                 url_value=None,
                 version=None):
        super(ItxLsThingLsThingValue, self).__init__(id=id, blob_value=blob_value, clob_value=clob_value, code_kind=code_kind, code_origin=code_origin,
                                                     code_type=code_type, code_value=code_value, comments=comments, conc_unit=conc_unit,
                                                     concentration=concentration, date_value=date_value, deleted=deleted, file_value=file_value, ignored=ignored,
                                                     ls_type=ls_type, ls_kind=ls_kind, ls_transaction=ls_transaction, modified_by=modified_by,
                                                     modified_date=modified_date, number_of_replicates=number_of_replicates, numeric_value=numeric_value,
                                                     operator_kind=operator_kind, operator_type=operator_type, public_data=public_data, recorded_by=recorded_by,
                                                     recorded_date=recorded_date, sig_figs=sig_figs, string_value=string_value, uncertainty=uncertainty,
                                                     uncertainty_type=uncertainty_type, unit_kind=unit_kind, unit_type=unit_type, url_value=url_value,
                                                     version=version)
        self.ls_state = ls_state


class SimpleLsThing(BaseModel):
    """The SimpleLsThing class is meant to vastly simplify how a programmer interacts with ACAS LsThing objects.
    This class buries the complexities of LsThings, LsStates, LsValues, LsLabels, and interactions into a simplified interface,
    and handles the conversions and updates to underlying ACAS LsThing classes to allow a python programmer to stick to editing
    much simpler dictionary objects.

    ACAS LsThings are "generic entities", meaning that they can be used to represent many different types of data. Across ACAS,
    the ls_type and ls_kind attributes are used to specify the meaning of an individual entity, label, value, or state.

    Top-level attributes (mapped directly onto the LsThing):
     - ls_type: The broadest classifier for what class of entities this LsThing represents.
     - ls_kind: A more specific classifier for what class of entities this LsThing represents.
     - code_name: Unique internal identifier, auto-generated by ACAS. Every LsThing with the same ls_type and ls_kind shares a
                  sequence of code_names with incrementing numbers.
     - recorded_by: The username of the person that recorded or saved this LsThing to ACAS. This is used for auditing and tracking
                    down the provenance of data.

    Identifiers (mapped onto LsThingLabels):
     - ids: IDs, often unique identifiers that can be used to reference this LsThing or to align this LsThing with entries in
            external data sources.
     - names: Human-readable names for this LsThing.
     - aliases: Additional non-primary identifiers. Notably different from `ids` and `names`, `aliases` allow for multiple
                labels of the same category (i.e. same ls_kind).

    Metadata and Results (mapped onto LsThingStates and LsThingValues):
     - metadata: Section for saving metadata about this entity. Highly flexible.
     - results: Section for saving data or results about this entity. Also highly flexible.

    State Tables (mapped onto LsThingStates and LsThingValues):
     - Stores tabular data with multiple "rows" of data with defined "columns".

    Links (Mapped onto ItxLsThingLsThing): Express relationships to other entities.

    Example storing "Toto" from the Wizard of Oz:
    ```
    {
        'ls_type': 'animal',
        'ls_kind': 'dog',
        'code_name': 'DOG00001',
        'recorded_by': 'bob',
        'ids': {
            'Dog License Number': 'DL0023114'
        },
        'names': {
            'Full Name': 'Terry'
        },
        'aliases': {
            'Character Name': ['Toto', 'Rex']
        },
        'metadata': {
            'Vital Records': {
                'Birth Date': -1139961600000
                'Death Date': -767923200000,
                'Birth City': 'Chicago'
                'Death City': 'Hollywood'
            }
        },
        'state_tables': {
            ('credits', 'Film'): {
                '0':{
                    'Movie Title': 'The Wizard of Oz',
                    'Release Year': 1939
                },
                '1':{
                    'Movie Title': 'The Women',
                    'Release Year': 1939
                }
            }
        }
        'results': {
            'Wikipedia': {
                'Wikipedia Page': 'https://en.wikipedia.org/wiki/Terry_(dog)'
            }
            'IMDB': {
                'Total Film Appearances': 16,
            }
        },
        'links': [
            {
                'verb': 'is owned by',
                'linked_thing': {
                    'ls_type': 'animal',
                    'ls_kind': 'human',
                    'code_name': 'HUM00001',
                    'names': {
                        'Full Name': 'Carl Spitz'
                    }
                }
            }
        ]

    }
    ```
    """
    _fields = ['ls_type', 'ls_kind', 'code_name', 'names', 'ids', 'aliases', 'metadata', 'results', 'links', 'recorded_by',
               'state_tables']

    ROW_NUM_KEY = 'row number'
    ID_LS_TYPE = 'id'
    NAME_LS_TYPE = 'name'
    ALIAS_LS_TYPE = 'alias'
    METADATA_LS_TYPE = 'metadata'
    RESULTS_LS_TYPE = 'results'

    def __init__(self, ls_type=None, ls_kind=None, code_name=None, names=None, ids=None, aliases=None, metadata=None, results=None, links=None, recorded_by=None,
                 preferred_label_kind=None, state_tables=None, ls_thing=None, client=None):
        self._client = client
        self.preferred_label_kind = preferred_label_kind
        # if ls_thing passed in, just parse from it and ignore the rest
        if ls_thing:
            self.populate_from_ls_thing(ls_thing)
        # Instantiate objects if they don't already exist
        else:
            self.ls_type = ls_type
            self.ls_kind = ls_kind
            self.code_name = code_name
            self.links = links or []
            metadata = metadata or {}
            self._init_metadata = copy.deepcopy(metadata)
            self.recorded_by = recorded_by
            self._ls_thing = LsThing(ls_type=self.ls_type, ls_kind=self.ls_kind,
                                     code_name=self.code_name, recorded_by=self.recorded_by)
            self.names = names or {}
            self.ids = ids or {}
            self.aliases = aliases or {}
            # Create empty dicts for LsLabels, LsStates, and LsValues
            # These will be populated by the "_prepare_for_save" method
            self._name_labels = {}
            self._id_labels = {}
            self._alias_labels = defaultdict(list)
            self.metadata = metadata
            self.results = results or {}
            self._metadata_states = {}
            self._metadata_values = {}
            self._results_states = {}
            self._results_values = {}
            self.state_tables = state_tables or defaultdict(dict)
            self._state_table_states = defaultdict(dict)
            self._state_table_values = defaultdict(lambda: defaultdict(dict))

    def populate_from_ls_thing(self, ls_thing):
        """Translates an LsThing object into the "simple" dictionary

        :param ls_thing: instance of class LsThing
        :type ls_thing: LsThing
        """
        self.ls_type = ls_thing.ls_type
        self.ls_kind = ls_thing.ls_kind
        self.code_name = ls_thing.code_name
        self.recorded_by = ls_thing.recorded_by
        self._ls_thing = ls_thing
        # Split out labels by ls_type into three categories
        self._name_labels = {
            label.ls_kind: label for label in ls_thing.ls_labels if label.ls_type == self.NAME_LS_TYPE and label.ignored is False}
        self._id_labels = {
            label.ls_kind: label for label in ls_thing.ls_labels if label.ls_type == self.ID_LS_TYPE and label.ignored is False}
        self._alias_labels = defaultdict(list)
        for label in ls_thing.ls_labels:
            if label.ls_type == self.ALIAS_LS_TYPE and label.ignored is False:
                self._alias_labels[label.ls_kind].append(label)
        # Names and IDs are simple - only expect one label for each ls_kind
        self.names = {ls_kind: label.label_text for ls_kind,
                      label in self._name_labels.items()}
        self.ids = {ls_kind: label.label_text for ls_kind,
                    label in self._id_labels.items()}
        # Aliases can have multiple labels with the same ls_kind
        self.aliases = defaultdict(list)
        for ls_kind, label_list in self._alias_labels.items():
            self.aliases[ls_kind].extend(
                [label.label_text for label in label_list])
        # State Tables: Multiple non-ignored states with the same lsType and lsKind
        all_states = {}
        for ls_state in ls_thing.ls_states:
            key = (ls_state.ls_type, ls_state.ls_kind)
            if key in all_states:
                all_states[key].append(ls_state)
            else:
                all_states[key] = [ls_state]
        # Parse out state type/kind and "row number" to form key for states within state tables
        self._state_table_states = defaultdict(dict)
        self._state_table_values = defaultdict(lambda: defaultdict(dict))
        self.state_tables = defaultdict(dict)
        for key, state_list in all_states.items():
            for state in state_list:
                if state.ignored is False:
                    vals_dict = parse_values_into_dict(state.ls_values)
                    # Row number must be present to recognize as a state table
                    if ROW_NUM_KEY in vals_dict:
                        row_num = vals_dict[ROW_NUM_KEY]
                        self._state_table_states[key][row_num] = state
                        self.state_tables[key][row_num] = parse_values_into_dict(
                            state.ls_values)
                        self._state_table_values[key][row_num] = get_lsKind_to_lsvalue(
                            state.ls_values)
        # "Normal" states, which are unique by type + kind
        single_states = [state for state_list in all_states.values()
                         for state in state_list if len(state_list) == 1]
        # metadata
        self._metadata_states = {
            state.ls_kind: state for state in single_states if state.ls_type == self.METADATA_LS_TYPE and state.ignored is False}
        self._metadata_values = {state_kind: {value.ls_kind if (value.unit_kind is None or value.unit_kind == "") else f"{value.ls_kind} ({value.unit_kind})":
                                              value for value in state.ls_values if value.ignored is False} for state_kind, state in self._metadata_states.items()}
        self.metadata = parse_states_into_dict(self._metadata_states)
        self._init_metadata = copy.deepcopy(self.metadata)
        # results
        self._results_states = {
            state.ls_kind: state for state in single_states if state.ls_type == self.RESULTS_LS_TYPE and state.ignored is False}
        self._results_values = {state_kind: {value.ls_kind if (value.unit_kind is None or value.unit_kind == "") else f"{value.ls_kind} ({value.unit_kind})":
                                             value for value in state.ls_values if value.ignored is False} for state_kind, state in self._results_states.items()}
        self.results = parse_states_into_dict(self._results_states)
        self._init_results = copy.deepcopy(self.results)
        # Parse interactions into Links
        parsed_links = []
        for itx in ls_thing.first_ls_things:
            if itx.ignored is False and itx.first_ls_thing.ignored is False:
                link = SimpleLink(itx_ls_thing_ls_thing=itx)
                parsed_links.append(link)
        for itx in ls_thing.second_ls_things:
            if itx.ignored is False and itx.second_ls_thing.ignored is False:
                link = SimpleLink(itx_ls_thing_ls_thing=itx)
                parsed_links.append(link)
        self.links = parsed_links

    def set_client(self, client):
        """
        Set ACAS database client.
        :param client: ACAS database client.
        :type client: acasclient.client
        """
        self._client = client

    def _convert_values_to_objects(self, values_dict, state):
        values_obj_dict = {}
        ls_values = []
        for val_kind, val_value in values_dict.items():
            if val_value is not None:
                # Handle lists within the value dict
                if isinstance(val_value, list):
                    new_ls_val = [make_ls_value(
                        LsThingValue, val_kind, val, self.recorded_by) for val in val_value]
                    ls_values.extend(new_ls_val)
                else:
                    new_ls_val = make_ls_value(
                        LsThingValue, val_kind, val_value, self.recorded_by)
                    ls_values.append(new_ls_val)
                values_obj_dict[val_kind] = new_ls_val
        state.ls_values = ls_values
        return state, values_obj_dict

    def as_dict(self):
        my_dict = super(SimpleLsThing, self).as_dict()
        link_dicts = []
        for link in self.links:
            link_dicts.append(link.as_dict())
        my_dict['links'] = link_dicts

        # Check metadata for CodeValues/BlobValue and convert them to dicts
        metadata = {}
        for key, val in self.metadata.items():
            metadata[key] = {}
            for k, v in val.items():
                if isinstance(v, CodeValue) or isinstance(v, BlobValue):
                    v = v.as_dict()
                metadata[key][k] = v
        my_dict[self.METADATA_LS_TYPE] = metadata

        # Check results for CodeValues/BlobValue and convert them to dicts
        results = {}
        for key, val in self.results.items():
            results[key] = {}
            for k, v in val.items():
                if isinstance(v, CodeValue) or isinstance(v, BlobValue):
                    v = v.as_dict()
                results[key][k] = v
        my_dict[self.RESULTS_LS_TYPE] = results

        return my_dict

    def get_preferred_label(self):
        return self._ls_thing.get_preferred_label()

    def pretty_print(self):
        my_dict = {}
        my_dict['Links'] = {}
        for link in self.links:
            my_dict['Links'][link.verb] = None
            preferredLabel = link.object.get_preferred_label()
            if preferredLabel:
                if preferredLabel.label_text:
                    my_dict['Links'][link.verb] = preferredLabel.label_text

        # Check metadata for CodeValues and convert them to dicts
        for key, val in self.metadata.items():
            my_dict[key] = {}
            for k, v in val.items():
                if isinstance(v, CodeValue):
                    v = v.code
                my_dict[key][k] = v

        # Check results for CodeValues and convert them to dicts
        for key, val in self.results.items():
            my_dict[key] = {}
            for k, v in val.items():
                if isinstance(v, CodeValue):
                    v = v.code
                my_dict[key][k] = v

        return my_dict

    def _prepare_for_save(self, client, user=None, upload_files=True):
        """Translates all changes made to the "simple dict" attributes of this object
        into the underlying LsThing / LsState / LsValue / LsLabel data models, to prepare
        for saving updates to the ACAS server.

        :param client: Authenticated instance of acasclient.client
        :type client: acasclient.client
        :param user: Username to record as having made these changes, defaults to self.recorded_by
        :type user: str, optional
        :param upload_files: Whether or not to automatically upload files to ACAS for new FileValues, defaults to True.
        :type upload_files: bool
        """
        # TODO redo recorded_by logic to allow passing in of an updater
        if not user:
            user = self.recorded_by
        # Detect value updates, apply ignored / modified by /modified date and create new value
        metadata_ls_states = update_ls_states_from_dict(
            LsThingState, self.METADATA_LS_TYPE, LsThingValue, self.metadata, self._metadata_states, self._metadata_values, user,
            client, upload_files)
        results_ls_states = update_ls_states_from_dict(
            LsThingState, self.RESULTS_LS_TYPE, LsThingValue, self.results, self._results_states, self._results_values, user,
            client, upload_files)
        state_tables_ls_states = update_state_table_states_from_dict(
            LsThingState, LsThingValue, self.state_tables, self._state_table_states, self._state_table_values, user,
            client, upload_files)
        self._ls_thing.ls_states = metadata_ls_states + \
            results_ls_states + state_tables_ls_states
        # Same thing for labels
        id_ls_labels = update_ls_labels_from_dict(
            LsThingLabel, self.ID_LS_TYPE, self.ids, self._id_labels, user, preferred_label_kind=self.preferred_label_kind)
        names_ls_labels = update_ls_labels_from_dict(
            LsThingLabel, self.NAME_LS_TYPE, self.names, self._name_labels, user, preferred_label_kind=self.preferred_label_kind)
        alias_ls_labels = update_ls_labels_from_dict(
            LsThingLabel, self.ALIAS_LS_TYPE, self.aliases, self._alias_labels, user, preferred_label_kind=self.preferred_label_kind)
        self._ls_thing.ls_labels = id_ls_labels + names_ls_labels + alias_ls_labels
        # Transform links into interactions
        first_ls_things = []
        second_ls_things = []
        for link in self.links:
            # Put "forwards" or "downstream" interactions into second_ls_things,
            # and "backwards" or "upstream" interactions into first_ls_things
            if link.forwards:
                second_ls_things.append(link._itx_ls_thing_ls_thing)
            else:
                first_ls_things.append(link._itx_ls_thing_ls_thing)
        self._ls_thing.first_ls_things = first_ls_things
        self._ls_thing.second_ls_things = second_ls_things

    def _cleanup_after_save(self):
        self.populate_from_ls_thing(self._ls_thing)

    def save(self, client):
        """Persist changes to the ACAS server.

        :param client: Authenticated instances of acasclient.client
        :type client: acasclient.client
        """
        self._prepare_for_save(client)
        # Persist
        self._ls_thing = self._ls_thing.save(client)
        self._cleanup_after_save()

    @classmethod
    def get_by_code(cls, code_name, client=None, ls_type=None, ls_kind=None):
        """Fetch a SimpleLsThing object from the ACAS server by ls_type + ls_kind + code_name

        :param code_name: code_name of LsThing to fetch
        :type code_name: str
        :param client: Authenticated instance of acasclient.client, defaults to None
        :type client: acasclient.client, optional
        :param ls_type: ls_type of LsThing to fetch, defaults to None
        :type ls_type: str, optional
        :param ls_kind: ls_kind of LsThing to fetch, defaults to None
        :type ls_kind: str, optional
        :return: SimpleLsThing object with latest data fetched frm the ACAS server
        :rtype: SimpleLsThing
        """
        if not ls_type:
            ls_type = cls.ls_type
        if not ls_kind:
            ls_kind = cls.ls_kind
        camel_case_dict = client.get_ls_thing(ls_type, ls_kind, code_name)
        simple_ls_thing = cls(ls_thing=LsThing.from_camel_dict(data=camel_case_dict))
        simple_ls_thing.set_client(client=client)
        return simple_ls_thing

    @classmethod
    def save_list(cls, client, models):
        """Persist a list of new SimpleLsThing objects to the ACAS server

        :param client: Authenticated instance of acasclient.client
        :type client: acasclient.client
        :param models: List of SimpleLsThing objects to save
        :type models: list
        :return: Updated list of SimpleLsThing objects after save
        :rtype: list
        """
        if len(models) == 0:
            return []

        for model in models:
            model._prepare_for_save(client)
        things_to_save = [model._ls_thing for model in models]
        camel_dict = [ls_thing.as_camel_dict() for ls_thing in things_to_save]
        saved_ls_things = client.save_ls_thing_list(camel_dict)
        return [cls(ls_thing=LsThing.from_camel_dict(ls_thing)) for ls_thing in saved_ls_things]

    @classmethod
    def update_list(cls, client, models, clear_links=False):
        """Persist updates for a list of existing SimpleLsThing objects to the ACAS server

        :param client: Authenticated instance of acasclient.client
        :type client: acasclient.client
        :param models: List of SimpleLsThing objects to update
        :type models: list
        :return: Updated list of SimpleLsThing objects after update
        :rtype: list
        """
        if len(models) == 0:
            return []

        for model in models:
            if clear_links:
                # clear out the links (interactions) to avoid updating the same linked `LsThing`
                # multiple times if two or more `model`s contain links to the same `LsThing`
                model.links = []
            model._prepare_for_save(client)
        things_to_save = [model._ls_thing for model in models]
        camel_dict = [ls_thing.as_camel_dict() for ls_thing in things_to_save]
        saved_ls_things = client.update_ls_thing_list(camel_dict)
        return [cls(ls_thing=LsThing.from_camel_dict(ls_thing)) for ls_thing in saved_ls_things]

    def get_file_hash(self, file_path):
        BLOCKSIZE = 65536
        hasher = hashlib.sha1()
        with open(file_path, "rb") as file_ref:
            buf = file_ref.read(BLOCKSIZE)
            while len(buf) > 0:
                hasher.update(buf)
                buf = file_ref.read(BLOCKSIZE)
        return(hasher.hexdigest())

    def add_link(self, verb=None, linked_thing=None, recorded_by=None, metadata=None, results=None, subject_type=None, **kwargs):
        """Create a new link between this SimpleLsThing and another SimpleLsThing `linked_thing`

        :param verb: The nature of the link. This should be defined in `interactions.py`, defaults to None
        :type verb: str, optional
        :param linked_thing: The "other" SimpleLsThing to create a link to, defaults to None
        :type linked_thing: SimpleLsThing, optional
        :param recorded_by: Username to record as having created the link, defaults to None
        :type recorded_by: str, optional
        :param metadata: Dictionary of metadata to associate with the link itself, defaults to {}
        :type metadata: dict, optional
        :param results: Dictionary of results to associate with the link itself, defaults to {}
        :type results: dict, optional
        :param subject_type: The type of the subject of the link, defaults to the ls_type of itself
        :type subject_type: str, optional
        """
        if not subject_type:
            subject_type = self.ls_type
        self.links.append(SimpleLink(verb=verb, object=linked_thing, recorded_by=recorded_by, metadata=metadata or {},
                          subject_type=subject_type, results=results or {}, **kwargs))

    def upload_file_values(self, client):
        """Loop through the values for file values and check if the value is a base64 string or
        a dict object.  If its either, then upload the file and replace the value
        with the relative path on the server (just the file name), required for the
        service route to properly handle the file on save of the LsThing.

        :param client: Authenticated instance of acasclient.client
        :type client: acasclient.client
        """
        def isBase64(s):
            return (len(s) % 4 == 0) and re.match('^[A-Za-z0-9+/]+[=]{0,2}$', s)

        def _upload_file_values_from_state_dict(state_dict):
            for state_kind, values_dict in state_dict.items():
                for value_kind, file_val in values_dict.items():
                    if isinstance(file_val, FileValue):
                        if file_val and file_val.value:
                            file_val = _upload_file_value(file_val, client)
                            state_dict[state_kind][value_kind] = file_val
            return state_dict
        self.metadata = _upload_file_values_from_state_dict(self.metadata)
        self.results = _upload_file_values_from_state_dict(self.results)


class SimpleLink(BaseModel):
    """The SimpleLink class is used to save directional relationships between SimpleLsThings. ACAS's LsThing data model is conceptually made
    up of nodes and edges in a "graph", where SimpleLsThings are the nodes and SimpleLinks are the edges. In this data model, the
    edges can be "rich" with data similar to the nodes.

    The relationships or links between SimpleLsThings are organized using verbs, such that the "first" SimpleLsThing, the SimpleLink "verb"
    and the "second" SimpleLsThing form an English "subject verb object" phrase.

    Following the example provided in SimpleLsThing of the dog actor Terry and her owner Carl Spitz, the relationship can be expressed as
    "Carl Spritz owns Terry", where subject="Carl Spritz", verb="owns", object="Terry".

    Looking directly at this relationship as a SimpleLink, it would appear as:

    ```
    {
        'verb': 'owns',
        'subject': {
            'ls_type': 'animal',
            'ls_kind': 'human',
            'code_name': 'HUM00001',
            'names': {
                'Full Name': 'Carl Spitz'
            }
        },
        'object': {
            'ls_type': 'animal',
            'ls_kind': 'dog',
            'code_name': 'DOG00001',
            'names': {
                'Full Name': 'Terry'
            },
        }
    }
    ```

    """
    _fields = ['verb', 'subject', 'object', 'metadata', 'results']

    def __init__(self, verb=None, subject=None, object=None, metadata=None, results=None, recorded_by=None, itx_ls_thing_ls_thing=None,
                 subject_type=None, object_type=None):
        """
        Create a link of form: "{subject} {verb} {object}" where {subject} and {object} are instances of SimpleLsThing
        examples: "{batch} {instantiates} {parent}", "{literature reference} {contains} {pdb structure}"
        """
        # if ItxLsThingLsThing passed in, parse it and ignore the rest
        if itx_ls_thing_ls_thing:
            self._itx_ls_thing_ls_thing = itx_ls_thing_ls_thing
            self.code_name = itx_ls_thing_ls_thing.code_name
            self.subject = None
            # metadata
            self._metadata_states = {
                state.ls_kind: state for state in itx_ls_thing_ls_thing.ls_states if state.ls_type == self.METADATA_LS_TYPE and state.ignored is False}
            self._metadata_values = {state_kind: {value.ls_kind: value for value in state.ls_values}
                                     for state_kind, state in self._metadata_states.items()}
            self.metadata = parse_states_into_dict(self._metadata_states)
            self._init_metadata = copy.deepcopy(self.metadata)
            # results
            self._results_states = {
                state.ls_kind: state for state in itx_ls_thing_ls_thing.ls_states if state.ls_type == self.RESULTS_LS_TYPE and state.ignored is False}
            self._results_values = {state_kind: {value.ls_kind: value for value in state.ls_values}
                                    for state_kind, state in self._results_states.items()}
            self.results = parse_states_into_dict(self._results_states)
            self._init_results = copy.deepcopy(self.results)
            # Interaction passed in will often be missing either the first_ls_thing or the second_ls_thing
            # if it comes from an interaction nested within an LsThing. In that case, the "parent" LsThing is always the subject.
            # Detect which one is missing to figure out which is the "parent" in the current "view"
            if itx_ls_thing_ls_thing.second_ls_thing and not itx_ls_thing_ls_thing.first_ls_thing:
                # First LsThing is the "parent" so we are looking "forward" and the verb is the ls_type
                self.forwards = True
                self.verb = itx_ls_thing_ls_thing.ls_type
                self.object = SimpleLsThing(
                    ls_thing=itx_ls_thing_ls_thing.second_ls_thing)
            if itx_ls_thing_ls_thing.first_ls_thing and not itx_ls_thing_ls_thing.second_ls_thing:
                # Second LsThing is the "parent", so we are looking "backward" and the verb needs to be reversed
                self.forwards = False
                self.verb = opposite(itx_ls_thing_ls_thing.ls_type)
                self.object = SimpleLsThing(
                    ls_thing=itx_ls_thing_ls_thing.first_ls_thing)
            if itx_ls_thing_ls_thing.first_ls_thing and itx_ls_thing_ls_thing.second_ls_thing:
                raise ValueError(
                    'Parsing non-nested interactions has not been implemented yet!')
        else:
            self.verb = verb
            self.subject = subject
            self.object = object
            self.recorded_by = recorded_by
            metadata = metadata or {}
            self.metadata = metadata
            results = results or {}
            self.results = results
            self._init_metadata = copy.deepcopy(metadata)
            self._init_results = copy.deepcopy(results)
            # If verb is recognized as one of our "forward" verbs, save the relationship normally
            first_ls_thing = None
            second_ls_thing = None
            if verb in INTERACTION_VERBS_DICT:
                self.forwards = True
                ls_type = verb
                if subject:
                    first_ls_thing = subject._ls_thing
                    first_type = subject.ls_type
                # If subject_type is provided, use it instead of the subject's ls_type
                if subject_type:
                    first_type = subject_type
                if object:
                    second_ls_thing = object._ls_thing
                    second_type = object.ls_type
                # If object_type is provided, use it instead of the objects's ls_type
                if object_type:
                    second_type = object_type
            else:
                # verb must be one of our "backward" verbs, so save the inverse of the relationship so we don't duplicate interaction
                self.forwards = False
                ls_type = opposite(verb)
                if object:
                    first_ls_thing = object._ls_thing
                    first_type = object.ls_type
                # If object_type is provided, use it instead of the objects's ls_type
                if object_type:
                    first_type = object_type
                if subject:
                    second_ls_thing = subject._ls_thing
                    second_type = subject.ls_type
                # If subject_type is provided, use it instead of the subject's ls_type
                if subject_type:
                    second_type = subject_type
            # print("First: ", first_type)
            # print("Second: ", second_type)
            ls_kind = '{}_{}'.format(first_type, second_type)
            self._itx_ls_thing_ls_thing = ItxLsThingLsThing(ls_type=ls_type, ls_kind=ls_kind, recorded_by=self.recorded_by,
                                                            first_ls_thing=first_ls_thing, second_ls_thing=second_ls_thing)
            # Parse metadata into states and values
            self._metadata_states = {}
            self._metadata_values = {}
            for state_kind, values_dict in metadata.items():
                metadata_state = ItxLsThingLsThingState(
                    ls_type=self.METADATA_LS_TYPE, ls_kind=state_kind, recorded_by=self.recorded_by)
                self._metadata_values[state_kind] = {}
                metadata_state, values_obj_dict = self._convert_values_to_objects(
                    values_dict, metadata_state)
                self._metadata_values[state_kind] = values_obj_dict
                self._metadata_states[state_kind] = metadata_state
            # Parse results into states and values
            self._results_states = {}
            self._results_values = {}
            for state_kind, values_dict in results.items():
                results_state = ItxLsThingLsThingState(
                    ls_type=self.RESULTS_LS_TYPE, ls_kind=state_kind, recorded_by=self.recorded_by)
                self._results_values[state_kind] = {}
                results_state, values_obj_dict = self._convert_values_to_objects(
                    values_dict, results_state)
                self._results_values[state_kind] = values_obj_dict
                self._results_states[state_kind] = results_state
            self._itx_ls_thing_ls_thing.ls_states = list(
                self._metadata_states.values()) + list(self._results_states.values())

    def _convert_values_to_objects(self, values_dict, state):
        """Converts simple dictionary values into ItxLsThingLsThingLsValues

        :param values_dict: simple dict of { value_kind: value }
        :type values_dict: dict
        :param state: ItxLsThingLsThingState to attached values to
        :type state: ItxLsThingLsThingState
        :return: Tuple of (updated state, ls_values_dict) where ls_values dict is of format { value_kind: LsValue }
        :rtype: tuple
        """
        values_obj_dict = {}
        ls_values = []
        for val_kind, val_value in values_dict.items():
            if val_value is not None:
                # Handle lists within the value dict
                if isinstance(val_value, list):
                    new_ls_val = [make_ls_value(
                        ItxLsThingLsThingValue, val_kind, val, self.recorded_by) for val in val_value]
                    ls_values.extend(new_ls_val)
                else:
                    new_ls_val = make_ls_value(
                        ItxLsThingLsThingValue, val_kind, val_value, self.recorded_by)
                    ls_values.append(new_ls_val)
            values_obj_dict[val_kind] = new_ls_val
        state.ls_values = ls_values
        return state, values_obj_dict

    def as_dict(self):
        my_dict = super(SimpleLink, self).as_dict()
        if self.subject:
            my_dict['subject'] = self.subject.as_dict()
        if self.object:
            my_dict['object'] = self.object.as_dict()
        return my_dict
