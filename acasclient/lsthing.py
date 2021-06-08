from __future__ import unicode_literals

import copy
import hashlib
import json
import logging
import pathlib
import re
from collections import defaultdict
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from .interactions import INTERACTION_VERBS_DICT, opposite

ROW_NUM_KEY = 'row number'

### JSON encoding / decoding

def camel_to_underscore(name):
    camel_pat = re.compile(r'([A-Z])')
    return camel_pat.sub(lambda x: '_' + x.group(1).lower(), name)

def underscore_to_camel(name):
    under_pat = re.compile(r'_([a-z])')
    return under_pat.sub(lambda x: x.group(1).upper(), name)

def convert_json(data, convert):
    if type(data) is list:
        new_data = []
        for val in data:
            new_data.append(convert_json(val, convert) if (isinstance(val, dict) or isinstance(val, list)) else val)
    elif type(data) is dict:
        new_data = {}
        for key, val in data.items():
            new_data[convert(key)] = convert_json(val, convert) if (isinstance(val, dict) or isinstance(val, list)) else val
    else:
        raise ValueError("Cannot convert {} to JSON: {}".format(type(data), data))
    return new_data

def datetime_to_ts(date):
    if date is None:
        return None
    return int(date.timestamp() * 1000)

def ts_to_datetime(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts / 1000)

from six import text_type as str


def ensure_string_list(list_to_convert):
    return [str(potential_integer) for potential_integer in list_to_convert]


## ACAS-specific conversion helpers
def parse_states_into_dict(ls_states_dict):
    """
    Parse a dict of LsStates with nested LsValues into a simpler dict of state_kind: { value_kind: value}
    Input:
        ls_states: dict of state_kind: LsState
    Output:
        state_dict: dictionary of state_kind: { value_kind : value}
    """
    state_dict = {}
    for state_kind, state in ls_states_dict.items():
        state_dict[state_kind] = parse_values_into_dict(state.ls_values)
    return state_dict

def parse_values_into_dict(ls_values):
    values_dict = {}
    for value in ls_values:
        if not value.ignored and not value.deleted:
            key = value.ls_kind
            if value.unit_kind is not None and value.unit_kind != "":
                key = f'{key} ({value.unit_kind})'
            if value.ls_type == 'stringValue':
                val = value.string_value
            elif value.ls_type == 'codeValue':
                val = DDictValue(value.code_value, code_type=value.code_type, code_kind=value.code_kind, code_origin=value.code_origin)
            elif value.ls_type == 'numericValue':
                val = value.numeric_value
            elif value.ls_type == 'dateValue':
                val = ts_to_datetime(value.date_value)
            elif value.ls_type == 'clobValue':
                val = clob(value.clob_value)
            elif value.ls_type == 'urlValue':
                val = value.url_value
            elif value.ls_type == 'fileValue':
                val = FileValue(value.file_value)
            elif value.ls_type == 'blobValue':
                val = BlobValue(value=value.blob_value, comments=value.comments)
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
    # Filter out ignored values
    ls_values = [v for v in ls_values_raw if not v.ignored and not v.deleted]
    lsKind_to_lsvalue = dict()
    for ls_value in ls_values:
        key = ls_value.ls_kind
        if key in lsKind_to_lsvalue:
            lsKind_to_lsvalue[key].append(ls_value)
        else:
            lsKind_to_lsvalue[key] = [ls_value]

    for ls_value in ls_values:
        key = ls_value.ls_kind
        val = lsKind_to_lsvalue[key]
        if len(val) == 1:
            lsKind_to_lsvalue[key] = val[0]

    return lsKind_to_lsvalue


def is_equal_ls_value_simple_value(ls_value, val):
    if (isinstance(val, list) and not isinstance(ls_value, list)) \
        or (isinstance(ls_value, list) and not isinstance(val, list)):
        return False
    elif isinstance(val, FileValue):
        return ls_value.file_value == val
    elif isinstance(val, BlobValue):
        return ls_value.blob_value == BlobValue(val.value, val.comments)
    elif isinstance(val, clob):
        return ls_value.clob_value == str(val)
    elif type(val) == str:
        if val.startswith('https://') or val.startswith('http://'):
            return ls_value.url_value == val
        else:
            return ls_value.string_value == val
    elif type(val) == bool:
        return ls_value.code_value == str(val)
    elif isinstance(val, DDictValue):
        return DDictValue(ls_value.code_value, ls_value.code_type, ls_value.code_kind, ls_value.code_origin) == val
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
            ddict = DDictValue(value.code_value, value.code_type,
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
        raise ValueError("Comparing values of type {} are not yet implemented!".format(type(val)))

def get_units_from_string(string):
    # Gets the units from strings,
    found_string = re.sub(r".*\((.*)\).*|(.*)", r"\1", string)
    units = None
    if found_string != "":
        units = found_string
    return units

def get_value_kind_without_extras(string):
    return re.sub(r"\[[^)]*\]","",re.sub(r"(.*)\((.*)\)(.*)", r"\1\3",re.sub(r"\{[^}]*\}","",string))).strip()

def make_ls_value(value_cls, value_kind, val, recorded_by):
    unit_kind = get_units_from_string(value_kind)
    value_kind = get_value_kind_without_extras(value_kind)
    if isinstance(val, FileValue):
        value = value_cls(ls_type="fileValue", ls_kind=value_kind, recorded_by=recorded_by,
                                                file_value=val, unit_kind = unit_kind)
    if isinstance(val, BlobValue):
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
                                                    clob_value=val, unit_kind = unit_kind)
        elif val.startswith('https://') or val.startswith('http://'):
            value = value_cls(ls_type='urlValue', ls_kind=value_kind, recorded_by=recorded_by,
                                                    url_value=val, unit_kind = unit_kind)
        else:
            value = value_cls(ls_type='stringValue', ls_kind=value_kind, recorded_by=recorded_by,
                                                    string_value=val, unit_kind = unit_kind)
    elif type(val) == bool or (isinstance(val, str) and val in ['true', 'false']):
        value = value_cls(ls_type='codeValue', ls_kind=value_kind, recorded_by=recorded_by,
                                                code_value=str(val).lower(), unit_kind = unit_kind)
    elif isinstance(val, DDictValue):
        value = value_cls(ls_type='codeValue', ls_kind=value_kind, recorded_by=recorded_by,
                            code_value=val.code, code_type=val.code_type, code_kind=val.code_kind, code_origin=val.code_origin, unit_kind = unit_kind)
    elif isinstance(val, float) or isinstance(val, int):
        if pd.isnull(val):
            val = None
        value = value_cls(ls_type='numericValue', ls_kind=value_kind, recorded_by=recorded_by,
                                                numeric_value=val, unit_kind = unit_kind)
    elif isinstance(val, datetime):
        value = value_cls(ls_type='dateValue', ls_kind=value_kind, recorded_by=recorded_by,
                                                date_value=datetime_to_ts(val), unit_kind = unit_kind)
    else:
        raise ValueError("Saving values of type {} are not yet implemented!".format(type(val)))
    return value

def update_ls_states_from_dict(state_class, state_type, value_class, state_value_simple_dict, ls_states_dict, ls_values_dict, edit_user):
    ls_states = []
    for state_kind, values_dict in state_value_simple_dict.items():
        try:
            state = ls_states_dict[state_kind]
        except KeyError:
            # state not found, so create one
            state = state_class(ls_type=state_type, ls_kind=state_kind, recorded_by=edit_user)
        try:
            current_values = ls_values_dict[state_kind]
        except KeyError:
            current_values = {}
        ls_values = update_ls_values_from_dict(value_class, values_dict, current_values, edit_user)
        state.ls_values = ls_values
        ls_states.append(state)
    return ls_states

def update_state_table_states_from_dict(state_class, value_class, state_table_simple_dict, state_table_states, state_table_values, edit_user):
    ls_states = []
    for type_kind_key, state_table in state_table_simple_dict.items():
        for row_num, values_dict in state_table.items():
            try:
                state = state_table_states[type_kind_key][row_num]
            except KeyError:
                # state not found, so create one
                state_type, state_kind = type_kind_key
                state = state_class(ls_type=state_type, ls_kind=state_kind, recorded_by=edit_user)
            # Ensure there is a row number value, and if not auto-create it
            if ROW_NUM_KEY not in values_dict:
                values_dict[ROW_NUM_KEY] = row_num
            try:
                current_values = state_table_values[type_kind_key][row_num]
            except KeyError:
                current_values = {}
            ls_values = update_ls_values_from_dict(value_class, values_dict, current_values, edit_user)
            state.ls_values = ls_values
            ls_states.append(state)
    return ls_states

def update_ls_values_from_dict(value_class, simple_value_dict, ls_values_dict, edit_user):
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
                    # Handle lists within the value dict
                    if new_val_is_list:
                        new_ls_vals = [make_ls_value(value_class, val_kind, val, edit_user) for val in val_value]
                        ls_values.extend(new_ls_vals)
                    else:
                        new_ls_val = make_ls_value(value_class, val_kind, val_value, edit_user)
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
                # New value of an ls_kind not seen before
                # Handle lists within the value dict
                    if new_val_is_list:
                        new_ls_vals = [make_ls_value(value_class, val_kind, val, edit_user) for val in val_value]
                        ls_values.extend(new_ls_vals)
                    else:
                        new_ls_val = make_ls_value(value_class, val_kind, val_value, edit_user)
                        ls_values.append(new_ls_val)
    return ls_values

def update_ls_labels_from_dict(label_class, label_type, simple_label_dict, ls_labels_dict, edit_user, preferred_label_kind=None):
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
                    preferred = False # preferred is not allowed for aliases
                    new_ls_label = label_class(ls_type=label_type, ls_kind=label_kind, label_text=new_label_text, preferred=preferred, recorded_by=edit_user)
                    ls_labels.append(new_ls_label)
        else:
            if label_kind in ls_labels_dict:
                old_ls_label = ls_labels_dict[label_kind]
                if old_ls_label.label_text != label_text:
                    # Label has changed. Mark old LsLabel as ignored and create  a new LsLabel
                    if label_text is not None:
                        preferred = (label_kind == preferred_label_kind)
                        new_ls_label = label_class(ls_type=label_type, ls_kind=label_kind, label_text=label_text, preferred=preferred, recorded_by=edit_user)
                        ls_labels.append(new_ls_label)
                    old_ls_label.ignored = True
                    old_ls_label.modified_by = edit_user
                    old_ls_label.modified_date = datetime_to_ts(datetime.now())
                ls_labels.append(old_ls_label)
            else:
                if label_text is not None:
                    # New label of an ls_kind not seen before
                    preferred = (label_kind == preferred_label_kind)
                    new_ls_label = label_class(ls_type=label_type, ls_kind=label_kind, label_text=label_text, preferred=preferred, recorded_by=edit_user)
                    ls_labels.append(new_ls_label)
    return ls_labels

class clob(str):
    pass

class FileValue(str):
    pass


class BlobValue(object):
    
    def __init__(self, value=None, comments=None):
        self.value = value
        self.comments = comments
    
    def __eq__(self, other: object) -> bool:
        return self.value == other.value and self.comments == other.comments


## Model classes

class BaseModel(object):
    _fields = ['id', 'ls_type', 'ls_kind', 'deleted', 'ignored', 'version']

    def __init__(self, id=None, ls_type=None, ls_kind=None, deleted=False, ignored=False, version=None):
        self.id = id
        self.ls_type = ls_type
        self.ls_kind = ls_kind
        self.deleted = deleted
        self.ignored = ignored
        self.version = version

    def as_dict(self):
        """
        :return: The instance as a dict
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
        snake_case_dict = self.as_dict()
        camel_dict = convert_json(snake_case_dict, underscore_to_camel)
        return camel_dict
    
    def as_json(self, **kwargs):
        """
        :return: The instance as a Json string
        """
        snake_case_dict = self.as_dict()
        camel_dict = convert_json(snake_case_dict, underscore_to_camel)
        return json.dumps(camel_dict, **kwargs)

    @classmethod
    def as_list(cls, models):
        return [model.as_dict() for model in models or []]
        
    @classmethod
    def as_json_list(cls, models):
        return json.dumps([json.loads(model.as_json()) for model in models or []])

    @classmethod
    def from_camel_dict(cls, data):
        snake_case_dict = convert_json(data, camel_to_underscore)
        return cls.from_dict(snake_case_dict)
    
    @classmethod
    def from_dict(cls, data):
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
        camel_dict = json.loads(data)
        snake_case_dict = convert_json(camel_dict, camel_to_underscore)
        return cls.from_dict(json.loads(data))

    @classmethod
    def from_list(cls, arr):
        return [cls.from_dict(elem) for elem in arr]

class DDictClass(object):
    # Data Dictionary Classes are controlled dictionaries of values
    # They're referenced by ls_thing_values of lsType "codeValue"
    _fields = ['code_type', 'code_kind', 'values']

    def __init__(self, type_kind, values):
        self.code_type, self.code_kind = type_kind
        self.values = values
        self.parser_map = {}
        for code, val_obj in self.values.items():
            accepted_vals = [code]
            if 'accepted_values' in val_obj:
                accepted_vals.extend(val_obj['accepted_values'])
            for val in accepted_vals:
                if val in self.parser_map and self.parser_map[val] != code:
                    raise ValueError('Invalid DDict definition for type/kind {}, {}. Accepted value "{}" is already being used by code "{}"'.format(self.code_type, self.code_kind, val, self.parser_map[val]))
                else:
                    self.parser_map[val.lower()] = code
    
    def parse(self, raw_str):
        safe_str = raw_str.lower()
        if safe_str in self.parser_map:
            return DDictValue(self.parser_map[safe_str], code_type=self.code_type, code_kind=self.code_kind, code_origin=self.code_origin)
        else:
            logger.error('Value "{}" not recognized for DDictClass "{}, {}, {}" - skipping!'.format(safe_str, self.code_type, self.code_kind, self.code_origin))
            return None

class DDictValue(object):
    _fields = ['code_type', 'code_kind','code_origin', 'code']

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
        """
        :return: Error message if the params provided are invalid else None
        :rtype: Union[str, None]
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

### Base ACAS entities, states, values, and interactions

class AbstractThing(BaseModel):

    _fields = BaseModel._fields + ['code_name', 'ls_transaction','modified_by', 'modified_date', 'recorded_by', 'recorded_date']

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
                recorded_by=None, # Should this and recorded_date be auto-filled-in here?
                recorded_date=None,
                version=None):
        super(AbstractThing, self).__init__(id=id, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
        self.code_name = code_name
        self.ls_transaction = ls_transaction
        self.modified_by = modified_by
        self.modified_date = modified_date
        self.recorded_by = recorded_by
        self.recorded_date = datetime_to_ts(datetime.now()) if recorded_date is None else recorded_date

class AbstractLabel(BaseModel):

    _fields = BaseModel._fields + ['image_file', 'label_text', 'ls_transaction','modified_date', 'physically_labled', 
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
                recorded_by=None, # Should this and recorded_date be auto-filled-in here?
                recorded_date=None,
                version=None):
        super(AbstractLabel, self).__init__(id=id, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
        self.image_file = image_file
        if len(label_text) > 255:
            raise ValueError('Label text "{}" exceeds max length of 255 characters. It is {} characters'.format(label_text, len(label_text)))
        self.label_text = label_text
        self.ls_transaction = ls_transaction
        self.modified_date = modified_date
        self.physically_labled = physically_labled
        self.preferred = preferred
        self.recorded_by = recorded_by
        self.recorded_date = datetime_to_ts(datetime.now()) if recorded_date is None else recorded_date

class AbstractState(BaseModel):

    _fields = BaseModel._fields + ['comments', 'ls_transaction', 'modified_by', 'modified_date', 'recorded_by', 'recorded_date']

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
                recorded_by=None, # Should this and recorded_date be auto-filled-in here?
                recorded_date=None,
                version=None):
        super(AbstractState, self).__init__(id=id, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
        self.comments = comments
        self.ls_transaction = ls_transaction
        self.modified_by = modified_by
        self.modified_date = modified_date
        self.recorded_by = recorded_by
        self.recorded_date = datetime_to_ts(datetime.now()) if recorded_date is None else recorded_date

class AbstractValue(BaseModel):

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
                recorded_by=None, # Should this and recorded_date be auto-filled-in here?
                recorded_date=None,
                sig_figs=None,
                string_value=None,
                uncertainty=None,
                uncertainty_type=None,
                unit_kind=None,
                unit_type=None,
                url_value=None,
                version=None):
        super(AbstractValue, self).__init__(id=id, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind, version=version)
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
        self.recorded_date = datetime_to_ts(datetime.now()) if recorded_date is None else recorded_date
        self.sig_figs = sig_figs
        self.string_value = string_value
        self.uncertainty = uncertainty
        self.uncertainty_type = uncertainty_type
        self.unit_kind = unit_kind
        self.unit_type = unit_type
        self.url_value = url_value

class LsThing(AbstractThing):

    _fields = AbstractThing._fields + ['ls_states', 'ls_labels', 'first_ls_things', 'second_ls_things']

    def __init__(self,
                id=None,
                code_name=None,
                deleted=False,
                first_ls_things=[],
                ignored=False,
                ls_labels=[],
                ls_type=None,
                ls_kind=None,
                ls_transaction=None,
                ls_states=[],
                modified_by=None,
                modified_date=None,
                recorded_by=None,
                recorded_date=None,
                second_ls_things=[],
                version=None):
        super(LsThing, self).__init__(id=id, code_name=code_name, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                        ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date, 
                        recorded_by=recorded_by, recorded_date=recorded_date, version=version)
        self.ls_states = ls_states
        self.ls_labels = ls_labels
        self.first_ls_things = first_ls_things
        self.second_ls_things = second_ls_things

    def get_preferred_label(self):
        for label in self.ls_labels:
            if not label.ignored and not label.deleted and label.preferred:
                return label

    def as_dict(self):
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
        if self.id and self.code_name:
            resp_dict = client.update_ls_thing_list([self.as_camel_dict()])
        else:
            resp_dict = client.save_ls_thing_list([self.as_camel_dict()])
        return LsThing.from_camel_dict(resp_dict[0])

class LsThingLabel(AbstractLabel):

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
                recorded_by=None, # Should this and recorded_date be auto-filled-in here?
                recorded_date=None,
                version=None):
        super(LsThingLabel, self).__init__(id=id, deleted=deleted, image_file=image_file, ignored=ignored, label_text=label_text, ls_type=ls_type,  
                        ls_kind=ls_kind, ls_transaction=ls_transaction, modified_date=modified_date, physically_labled=physically_labled, 
                        preferred=preferred, recorded_by=recorded_by, recorded_date=recorded_date, version=version)
        self.ls_thing = ls_thing

class LsThingState(AbstractState):

    _fields = AbstractState._fields + ['ls_values', 'ls_thing']

    def __init__(self,
                id=None,
                comments=None,
                deleted=False,
                ignored=False,
                ls_type=None,
                ls_kind=None,
                ls_transaction=None,
                ls_values=[],
                ls_thing=None,
                modified_by=None,
                modified_date=None,
                recorded_by=None,
                recorded_date=None,
                version=None):
        super(LsThingState, self).__init__(id=id, comments=comments, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                        ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date,
                        recorded_by=recorded_by,recorded_date=recorded_date,version=None)
        self.ls_values = ls_values
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
        super(LsThingValue, self).__init__(id=id,blob_value=blob_value,clob_value=clob_value,code_kind=code_kind,code_origin=code_origin,
                        code_type=code_type,code_value=code_value,comments=comments,conc_unit=conc_unit,
                        concentration=concentration,date_value=date_value,deleted=deleted,file_value=file_value,ignored=ignored,
                        ls_type=ls_type,ls_kind=ls_kind,ls_transaction=ls_transaction,modified_by=modified_by,
                        modified_date=modified_date,number_of_replicates=number_of_replicates,numeric_value=numeric_value,
                        operator_kind=operator_kind,operator_type=operator_type,public_data=public_data,recorded_by=recorded_by,
                        recorded_date=recorded_date,sig_figs=sig_figs,string_value=string_value,uncertainty=uncertainty,
                        uncertainty_type=uncertainty_type,unit_kind=unit_kind,unit_type=unit_type,url_value=url_value,
                        version=version)
        self.ls_state = ls_state

class ItxLsThingLsThing(AbstractThing):

    _fields = AbstractThing._fields + ['ls_states', 'first_ls_thing', 'second_ls_thing']

    def __init__(self,
                id=None,
                code_name=None,
                deleted=False,
                first_ls_thing=None,
                ignored=False,
                ls_type=None,
                ls_kind=None,
                ls_transaction=None,
                ls_states=[],
                modified_by=None,
                modified_date=None,
                recorded_by=None,
                recorded_date=None,
                second_ls_thing=None,
                version=None):
        super(ItxLsThingLsThing, self).__init__(id=id, code_name=code_name, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                        ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date, 
                        recorded_by=recorded_by, recorded_date=recorded_date, version=version)
        self.ls_states = ls_states
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
                ls_values=[],
                itx_ls_thing_ls_thing=None,
                modified_by=None,
                modified_date=None,
                recorded_by=None,
                recorded_date=None,
                version=None):
        super(ItxLsThingLsThingState, self).__init__(id=id, comments=comments, deleted=deleted, ignored=ignored, ls_type=ls_type, ls_kind=ls_kind,
                        ls_transaction=ls_transaction, modified_by=modified_by, modified_date=modified_date,
                        recorded_by=recorded_by,recorded_date=recorded_date,version=None)
        self.ls_values = ls_values
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
        super(ItxLsThingLsThingValue, self).__init__(id=id,blob_value=blob_value,clob_value=clob_value,code_kind=code_kind,code_origin=code_origin,
                        code_type=code_type,code_value=code_value,comments=comments,conc_unit=conc_unit,
                        concentration=concentration,date_value=date_value,deleted=deleted,file_value=file_value,ignored=ignored,
                        ls_type=ls_type,ls_kind=ls_kind,ls_transaction=ls_transaction,modified_by=modified_by,
                        modified_date=modified_date,number_of_replicates=number_of_replicates,numeric_value=numeric_value,
                        operator_kind=operator_kind,operator_type=operator_type,public_data=public_data,recorded_by=recorded_by,
                        recorded_date=recorded_date,sig_figs=sig_figs,string_value=string_value,uncertainty=uncertainty,
                        uncertainty_type=uncertainty_type,unit_kind=unit_kind,unit_type=unit_type,url_value=url_value,
                        version=version)
        self.ls_state = ls_state


class SimpleLsThing(BaseModel):
    _fields = ['ls_type', 'ls_kind', 'code_name', 'names', 'ids', 'aliases', 'metadata', 'results', 'links', 'recorded_by',
                'state_tables']
    
    ROW_NUM_KEY = 'row number'

    def __init__(self, ls_type=None, ls_kind=None, code_name=None, names={}, ids={}, aliases={}, metadata={}, results={}, links=[], recorded_by=None,
                preferred_label_kind=None, state_tables=defaultdict(dict), ls_thing=None):
        self.preferred_label_kind = preferred_label_kind
        # if ls_thing passed in, just parse from it and ignore the rest
        if ls_thing:
            self.populate_from_ls_thing(ls_thing)
        # Instantiate objects if they don't already exist
        else:
            self.ls_type = ls_type
            self.ls_kind = ls_kind
            self.code_name = code_name
            self.links = links
            self._init_metadata = copy.deepcopy(metadata)
            self.recorded_by = recorded_by
            self._ls_thing = LsThing(ls_type=self.ls_type, ls_kind=self.ls_kind, code_name=self.code_name, recorded_by=self.recorded_by)
            self.names = names
            self.ids = ids
            self.aliases = aliases
            # Create empty dicts for LsLabels, LsStates, and LsValues
            # These will be populated by the "_prepare_for_save" method
            self._name_labels = {}
            self._id_labels = {}
            self._alias_labels = defaultdict(list)
            self.metadata = metadata
            self.results = results
            self._metadata_states = {}
            self._metadata_values = {}
            self._results_states = {}
            self._results_values = {}
            self.state_tables = state_tables
            self._state_table_states = defaultdict(dict)
            self._state_table_values = defaultdict(lambda: defaultdict(dict))
    
    def populate_from_ls_thing(self, ls_thing):
        self.ls_type = ls_thing.ls_type
        self.ls_kind = ls_thing.ls_kind
        self.code_name = ls_thing.code_name
        self.recorded_by = ls_thing.recorded_by
        self._ls_thing = ls_thing
        # Split out labels by ls_type into three categories
        self._name_labels = {label.ls_kind: label for label in ls_thing.ls_labels if label.ls_type == 'name' and label.ignored == False}
        self._id_labels = {label.ls_kind: label for label in ls_thing.ls_labels if label.ls_type == 'id' and label.ignored == False}
        self._alias_labels = defaultdict(list)
        for label in ls_thing.ls_labels:
            if label.ls_type == 'alias' and label.ignored == False:
                self._alias_labels[label.ls_kind].append(label)
        # Names and IDs are simple - only expect one label for each ls_kind
        self.names = {ls_kind : label.label_text for ls_kind, label in self._name_labels.items()}
        self.ids = {ls_kind : label.label_text for ls_kind, label in self._id_labels.items()}
        # Aliases can have multiple labels with the same ls_kind
        self.aliases = defaultdict(list)
        for ls_kind, label_list in self._alias_labels.items():
            self.aliases[ls_kind].extend([label.label_text for label in label_list])
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
                if state.ignored == False:
                    vals_dict = parse_values_into_dict(state.ls_values)
                    # Row number must be present to recognize as a state table
                    if ROW_NUM_KEY in vals_dict:
                        row_num = vals_dict[ROW_NUM_KEY]
                        self._state_table_states[key][row_num] = state
                        self.state_tables[key][row_num] = parse_values_into_dict(state.ls_values)
                        self._state_table_values[key][row_num] = get_lsKind_to_lsvalue(state.ls_values)
        # "Normal" states, which are unique by type + kind
        single_states = [state for state_list in all_states.values() for state in state_list if len(state_list) == 1]
        # metadata
        self._metadata_states = {state.ls_kind: state for state in single_states if state.ls_type == 'metadata' and state.ignored == False}
        self._metadata_values = {state_kind : {value.ls_kind if (value.unit_kind==None or value.unit_kind == "") else f"{value.ls_kind} ({value.unit_kind})": value for value in state.ls_values if value.ignored == False} for state_kind, state in self._metadata_states.items()}
        self.metadata = parse_states_into_dict(self._metadata_states)
        self._init_metadata = copy.deepcopy(self.metadata)
        # results
        self._results_states = {state.ls_kind: state for state in single_states if state.ls_type == 'results' and state.ignored == False}
        self._results_values = {state_kind : {value.ls_kind if (value.unit_kind==None or value.unit_kind == "") else f"{value.ls_kind} ({value.unit_kind})": value for value in state.ls_values if value.ignored == False} for state_kind, state in self._results_states.items()}
        self.results = parse_states_into_dict(self._results_states)
        self._init_results = copy.deepcopy(self.results)
        # Parse interactions into Links
        parsed_links = []
        for itx in ls_thing.first_ls_things:
            if itx.ignored == False and itx.first_ls_thing.ignored == False:
                link = SimpleLink(itx_ls_thing_ls_thing = itx)
                parsed_links.append(link)
        for itx in ls_thing.second_ls_things:
            if itx.ignored == False and itx.second_ls_thing.ignored == False:
                link = SimpleLink(itx_ls_thing_ls_thing = itx)
                parsed_links.append(link)
        self.links = parsed_links

    def _convert_values_to_objects(self, values_dict, state):
        values_obj_dict = {}
        ls_values = []
        for val_kind, val_value in values_dict.items():
            if val_value is not None:
                # Handle lists within the value dict
                if isinstance(val_value, list):
                    new_ls_val = [make_ls_value(LsThingValue, val_kind, val, self.recorded_by) for val in val_value]
                    ls_values.extend(new_ls_val)
                else:
                    new_ls_val = make_ls_value(LsThingValue, val_kind, val_value, self.recorded_by)
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

        # Check metadata for DDictValues and convert them to dicts
        metadata = {}
        for key, val in self.metadata.items():
            metadata[key] = {}
            for k, v in val.items():
                if isinstance(v, DDictValue):
                    v = v.as_dict()
                metadata[key][k] = v
        my_dict['metadata'] = metadata

        # Check results for DDictValues and convert them to dicts
        results = {}
        for key, val in self.results.items():
            results[key] = {}
            for k, v in val.items():
                if isinstance(v, DDictValue):
                    v = v.as_dict()
                results[key][k] = v
        my_dict['results'] = results

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
    
        # Check metadata for DDictValues and convert them to dicts
        for key, val in self.metadata.items():
            my_dict[key] = {}
            for k, v in val.items():
                if isinstance(v, DDictValue):
                    v = v.code
                my_dict[key][k] = v

        # Check results for DDictValues and convert them to dicts
        results = {}
        for key, val in self.results.items():
            my_dict[key] = {}
            for k, v in val.items():
                if isinstance(v, DDictValue):
                    v = v.code
                my_dict[key][k] = v

        return my_dict

    def _prepare_for_save(self, client, user=None):
        #TODO redo recorded_by logic to allow passing in of an updater
        if not user:
            user = self.recorded_by
        #Detect value updates, apply ignored / modified by /modified date and create new value
        metadata_ls_states = update_ls_states_from_dict(LsThingState, 'metadata', LsThingValue, self.metadata, self._metadata_states, self._metadata_values, user)
        results_ls_states = update_ls_states_from_dict(LsThingState, 'results', LsThingValue, self.results, self._results_states, self._results_values, user)
        state_tables_ls_states = update_state_table_states_from_dict(LsThingState, LsThingValue, self.state_tables, self._state_table_states, self._state_table_values, user)
        self._ls_thing.ls_states = metadata_ls_states + results_ls_states + state_tables_ls_states
        # Same thing for labels
        id_ls_labels = update_ls_labels_from_dict(LsThingLabel, 'id', self.ids, self._id_labels, user, preferred_label_kind=self.preferred_label_kind)
        names_ls_labels = update_ls_labels_from_dict(LsThingLabel, 'name', self.names, self._name_labels, user, preferred_label_kind=self.preferred_label_kind)
        alias_ls_labels = update_ls_labels_from_dict(LsThingLabel, 'alias', self.aliases, self._alias_labels, user, preferred_label_kind=self.preferred_label_kind)
        self._ls_thing.ls_labels = id_ls_labels + names_ls_labels + alias_ls_labels
        #Transform links into interactions
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
        self._prepare_for_save(client)
        # Persist
        self._ls_thing = self._ls_thing.save(client)
        self._cleanup_after_save()
    
    @classmethod
    def get_by_code(cls, code_name, client=None, ls_type=None, ls_kind=None):
        if not ls_type:
            ls_type = cls.ls_type
        if not ls_kind:
            ls_kind = cls.ls_kind
        ls_thing = client.get_ls_thing(ls_type, ls_kind, code_name)
        return cls(ls_thing=ls_thing)
    
    @classmethod
    def save_list(cls, client, models):
        if len(models) == 0:
            return []

        for model in models:
            model._prepare_for_save(client)
        things_to_save = [model._ls_thing for model in models]
        #logger.info('THINGS TO SAVE')
        camel_dict = [ls_thing.as_camel_dict() for ls_thing in things_to_save]
        #logger.info(camel_dict)
        saved_ls_things = client.save_ls_thing_list(camel_dict)
        #logger.info(saved_ls_things)
        return [cls(ls_thing=LsThing.from_camel_dict(ls_thing)) for ls_thing in saved_ls_things]
    
    @classmethod
    def update_list(cls, client, models, clear_links=False):
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

    def add_link(self, verb=None, linked_thing=None, recorded_by=None, metadata={}, results={}):
        """
        Create a new link between this SimpleLsThing and another SimpleLsThing `linked_thing`
        """
        self.links.append(SimpleLink(verb=verb, object=linked_thing, subject_type=self.ls_type, 
                                    recorded_by=recorded_by, metadata=metadata, results=results))
    
    def upload_file_values(self, client):
        """
        Loop through the values for file values and check if the value is a base64 string or
        a dict object.  If its either, then upload the file and replace the value
        with the relative path on the server (just the file name), required for the 
        service route to properly handle the file on save of the ls thing.
        """
        def isBase64(s):
            return (len(s) % 4 == 0) and re.match('^[A-Za-z0-9+/]+[=]{0,2}$', s)
        def _upload_file_values_from_state_dict(state_dict):
            for state_kind, values_dict in state_dict.items():
                for value_kind, file_val in values_dict.items():
                    if isinstance(file_val, FileValue):
                        if file_val:
                            val = pathlib.Path(file_val)
                            uploaded_files = client.upload_files([val])
                            state_dict[state_kind][value_kind] = FileValue(uploaded_files['files'][0]['name'])
            return state_dict
        self.metadata = _upload_file_values_from_state_dict(self.metadata)
        self.results = _upload_file_values_from_state_dict(self.results)


class SimpleLink(BaseModel):
    _fields = ['verb', 'subject', 'object', 'metadata', 'results']

    def __init__(self, verb=None, subject=None, object=None, metadata={}, results={}, recorded_by=None, itx_ls_thing_ls_thing=None,
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
            self._metadata_states = {state.ls_kind: state for state in itx_ls_thing_ls_thing.ls_states if state.ls_type == 'metadata' and state.ignored == False}
            self._metadata_values = {state_kind : {value.ls_kind: value for value in state.ls_values} for state_kind, state in self._metadata_states.items()}
            self.metadata = parse_states_into_dict(self._metadata_states)
            self._init_metadata = copy.deepcopy(self.metadata)
            # results
            self._results_states = {state.ls_kind: state for state in itx_ls_thing_ls_thing.ls_states if state.ls_type == 'results' and state.ignored == False}
            self._results_values = {state_kind : {value.ls_kind: value for value in state.ls_values} for state_kind, state in self._results_states.items()}
            self.results = parse_states_into_dict(self._results_states)
            self._init_results = copy.deepcopy(self.results)
            # Interaction passed in will often be missing either the first_ls_thing or the second_ls_thing
            # if it comes from an interaction nested within an LsThing. In that case, the "parent" LsThing is always the subject.
            # Detect which one is missing to figure out which is the "parent" in the current "view"
            if itx_ls_thing_ls_thing.second_ls_thing and not itx_ls_thing_ls_thing.first_ls_thing:
                # First LsThing is the "parent" so we are looking "forward" and the verb is the ls_type
                self.forwards = True
                self.verb = itx_ls_thing_ls_thing.ls_type
                self.object = SimpleLsThing(ls_thing=itx_ls_thing_ls_thing.second_ls_thing)
            if itx_ls_thing_ls_thing.first_ls_thing and not itx_ls_thing_ls_thing.second_ls_thing:
                # Second LsThing is the "parent", so we are looking "backward" and the verb needs to be reversed
                self.forwards = False
                self.verb = opposite(itx_ls_thing_ls_thing.ls_type)
                self.object = SimpleLsThing(ls_thing=itx_ls_thing_ls_thing.first_ls_thing)
            if itx_ls_thing_ls_thing.first_ls_thing and itx_ls_thing_ls_thing.second_ls_thing:
                raise ValueError('Parsing non-nested interactions has not been implemented yet!')
        else:
            self.verb = verb
            self.subject = subject
            self.object = object
            self.recorded_by = recorded_by
            self.metadata = metadata
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
                else:
                    first_type = subject_type
                if object:
                    second_ls_thing = object._ls_thing
                    second_type = object.ls_type
                else:
                    second_type = object_type
            else:
                # verb must be one of our "backward" verbs, so save the inverse of the relationship so we don't duplicate interaction
                self.forwards = False
                ls_type = opposite(verb)
                if object:
                    first_ls_thing = object._ls_thing
                    first_type = object.ls_type
                else:
                    first_type = object_type
                if subject:
                    second_ls_thing = subject._ls_thing
                    second_type = subject.ls_type
                else:
                    second_type = subject_type
            # print("First: ", first_type)
            # print("Second: ", second_type)
            ls_kind = '{}_{}'.format(first_type, second_type)
            self._itx_ls_thing_ls_thing = ItxLsThingLsThing(ls_type=ls_type,ls_kind=ls_kind, recorded_by=self.recorded_by,
                                                            first_ls_thing=first_ls_thing, second_ls_thing=second_ls_thing)
            # Parse metadata into states and values
            self._metadata_states = {}
            self._metadata_values = {}
            for state_kind, values_dict in metadata.items():
                metadata_state = ItxLsThingLsThingState(ls_type='metadata', ls_kind=state_kind, recorded_by=self.recorded_by)
                self._metadata_values[state_kind] = {}
                metadata_state, values_obj_dict = self._convert_values_to_objects(values_dict, metadata_state)
                self._metadata_values[state_kind] = values_obj_dict
                self._metadata_states[state_kind] = metadata_state
            # Parse results into states and values
            self._results_states = {}
            self._results_values = {}
            for state_kind, values_dict in results.items():
                results_state = ItxLsThingLsThingState(ls_type='results', ls_kind=state_kind, recorded_by=self.recorded_by)
                self._results_values[state_kind] = {}
                results_state, values_obj_dict = self._convert_values_to_objects(values_dict, results_state)
                self._results_values[state_kind] = values_obj_dict
                self._results_states[state_kind] = results_state
            self._itx_ls_thing_ls_thing.ls_states = list(self._metadata_states.values()) + list(self._results_states.values())
        
    def _convert_values_to_objects(self, values_dict, state):
        values_obj_dict = {}
        ls_values = []
        for val_kind, val_value in values_dict.items():
            if val_value is not None:
                # Handle lists within the value dict
                if isinstance(val_value, list):
                    new_ls_val = [make_ls_value(ItxLsThingLsThingValue, val_kind, val, self.recorded_by) for val in val_value]
                    ls_values.extend(new_ls_val)
                else:
                    new_ls_val = make_ls_value(ItxLsThingLsThingValue, val_kind, val_value, self.recorded_by)
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
