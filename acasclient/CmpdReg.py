from __future__ import annotations
from .ddict import ACASDDict
from enum import Enum
import types
import logging
from .acasclient import client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class AdditionalScientistType(Enum):
    """Enum for additional scientist types."""
    COMPOUND = ACASDDict('compound', 'scientist')
    ASSAY = ACASDDict('assay', 'scientist')


class AdditionalScientist():
    """Additional Scientist class."""
    def __init__(self, type: AdditionalScientistType, id: int = None, code: str = None, name: str = None, ignored: bool = None):
        self.id = id
        self.ignored = ignored
        self.code = code
        self.name = name
        self.type = type

    def save(self, client: client) -> AdditionalScientist:
        """Save the scientist to the server."""
        if self.type == AdditionalScientistType.COMPOUND:
            resp = client.create_cmpdreg_scientist(self.code, self.name)
        elif self.type == AdditionalScientistType.ASSAY:
            resp = client.create_assay_scientist(self.code, self.name)
        self.id = resp['id']
        return self

    def as_dict(self) -> dict:
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'ignored': self.ignored,
            'type': self.type.name
        }


class AdditionalCompoundScientist(AdditionalScientist):
    """Additional Compound Scientist class."""

    def __init__(self, id: int = None, code: str = None, name: str = None, ignored: bool = None):
        super().__init__(AdditionalScientistType.COMPOUND, id, code, name, ignored)


class AdditionalAssayScientist(AdditionalScientist):
    """Additional Assay Scientist class."""

    def __init__(self, id: int = None, code: str = None, name: str = None, ignored: bool = None):
        super().__init__(AdditionalScientistType.ASSAY, id, code, name, ignored)


def meta_lots_to_dict_array(meta_lots: list[dict]) -> list[dict]:
    """Converts a list of meta lots to a list of flattened dictionaries which specific fields which are suitable for upload via CmpdReg BulkLoader."""
    return [meta_lot_to_dict(meta_lot) for meta_lot in meta_lots]


def meta_lot_to_dict(meta_lot: dict) -> dict:
    """Converts a meta lot to a dictionary into a flat dictionary of specific fields."""
    parent_common_names = [parent_alias["aliasName"] for parent_alias in meta_lot["lot"]["saltForm"]["parent"]["parentAliases"] if parent_alias["lsKind"] == "Common Name"]

    # Check for salts
    salt_abrevs = [iso_salt['salt']["abbrev"] for iso_salt in meta_lot["isosalts"]]
    salt_equivs = [str(iso_salt["equivalents"]) for iso_salt in meta_lot["isosalts"]]

    # Synthesis date is in the format MM/DD/YYYY
    # However Creg isn't good at converting the date back to the correct format
    # So we need to convert it to YYYY-MM-DD
    synthesis_date = meta_lot["lot"]["synthesisDate"]
    if synthesis_date is not None:
        synthesis_date = synthesis_date[6:] + '-' + synthesis_date[:2] + '-' + synthesis_date[3:5]

    # If lot amount is filled in, then we need to fill in lot barcode with the lot corp name
    lot_barcode = meta_lot["lot"]["corpName"] if meta_lot["lot"]["amount"] is not None else None

    return_dict = {
        'mol': meta_lot["lot"]['asDrawnStruct'] if meta_lot["lot"]['asDrawnStruct'] is not None else meta_lot["lot"]["parent"]["molStructure"],
        "id": meta_lot["lot"]["id"],
        "name": meta_lot["lot"]["corpName"],
        "parent_common_name": '; '.join(parent_common_names) if len(parent_common_names) > 0 else None,
        "parent_corp_name": meta_lot["lot"]["parent"]["corpName"],
        "lot_amount":  meta_lot["lot"]["amount"],
        "lot_amount_units":  meta_lot["lot"]["amountUnits"]["code"] if meta_lot["lot"]["amountUnits"] is not None else None,
        "lot_color": meta_lot["lot"]["color"],
        "lot_synthesis_date": synthesis_date,
        "lot_notebook_page": meta_lot["lot"]["notebookPage"],
        "lot_corp_name": meta_lot["lot"]["corpName"],
        "lot_number": meta_lot["lot"]["lotNumber"],
        "lot_purity": meta_lot["lot"]["purity"],
        "lot_purity_opertator": meta_lot["lot"]["purityOperator"]["code"] if meta_lot["lot"]["purityOperator"] is not None else None,
        "lot_comments": meta_lot["lot"]["comments"],
        "lot_chemist": meta_lot["lot"]["chemist"],
        "lot_solution_amount":  meta_lot["lot"]["solutionAmount"],
        "lot_solution_amount_units": meta_lot["lot"]["solutionAmountUnits"]["code"] if meta_lot["lot"]["solutionAmountUnits"] is not None else None,
        "lot_supplier": meta_lot["lot"]["supplier"],
        "lot_supplier_id": meta_lot["lot"]["supplierID"],
        "project": meta_lot["lot"]["project"],
        "parent_stereo_category": meta_lot["lot"]["parent"]["stereoCategory"]['code'],
        "parent_stereo_comment": meta_lot["lot"]["parent"]["stereoComment"],
        "lot_is_virtual": meta_lot["lot"]["isVirtual"],
        "lot_supplier_lot": meta_lot["lot"]["supplierLot"],
        "lot_salt_abbrev": '; '.join(salt_abrevs) if len(salt_abrevs) > 0 else None,
        "lot_salt_equivalents": '; '.join(salt_equivs) if len(salt_equivs) > 0 else None,
        "lot_barcode": lot_barcode
    }
    return return_dict


def convert_dict_to_type(dict: dict, type_name: str) -> object:
    """Converts a dictionary to a dynamic python type and instaniates a new object of that type.
    
    :param dict: The dictionary to convert
    :param type_name: The name of the new type
    :return: A new type with the keys of the dictionary as attributes
    """

    # Add a _fields attribute with the keys of the dictionary
    dict['_fields'] = list(dict.keys())

    # A method added to the dynamic type which can be used to conver the type back to a dictionary
    def as_dict(self) -> dict:
        """
        Return a map of attribute name and attribute values stored on the
        instance.
        Note: Only attributes stored in `FileValue._fields` will be returned.
        """
        return {
            field: getattr(self, field, None)
            for field in self._fields
        }

    # Create a new type with the dictionary as the attributes
    # and instantiates a new object of that type
    new_type = type(type_name, (object,), dict)()

    # Add the as_dict method to the new type
    new_type.as_dict = types.MethodType(as_dict, new_type)
    return new_type


def convert_object_to_sdf(object) -> str:
    """Converts an object to an SDF with each of the keys and values as mol properties.
    
    :param object: The object to convert which must have an as_dict method and a mol attribute
    :return: The object as an SDF
    """

    # Convert object to dictionary
    object_dict = object.as_dict()

    # Get the molfile
    molfile = object_dict['mol']

    # Remove the molfile from the dictionary
    del object_dict['mol']

    # Change the dict keys from snake case to space case
    object_dict = {key.replace('_', ' ').title(): value for key, value in object_dict.items()}

    # Strip any '$'s and newlines from the end of the molfile
    molfile = molfile.rstrip().rstrip('$').rstrip()

    # Format of SDF is:
    # {molfile}
    # >  <{key}>
    # {value}
    #
    # >  <{key}>
    # {value}
    #
    # $$$$
    # So we need to add the >  <{key}> to the beginning of each value
    object_dict = {f'>  <{key}>': value for key, value in object_dict.items()}

    # Join the object keys and values like the format above
    sdf = '\n'.join([f'{key}\n{value}\n' for key, value in object_dict.items() if value is not None and value != ''])

    # Add the molfile to the beginning of the sdf and add the $$$$ at the end
    sdf = f'{molfile}\n{sdf}\n$$$$'

    return sdf


def create_cmpd_reg_mapping_from_object(object) -> list[dict]:
    """Creates a compound registration mapping array of dictionaries from an object.
    
    Example input:
        {
            "lot_color": "Blue",
            "lot_corp_name": "Test Corp",
            "lot_number": "1",
            "parent_stereo_category": "R",
            "parent_stereo_comment": ,
            "lot_chemist": "Test Chemist"
        }
    Example output:
        [
            {
                "dbProperty": "Lot Color",
                "defaultVal": null,
                "required": false,
                "sdfProperty": "Lot Color"
            },
            {
                "dbProperty": "Lot Corp Name",
                "defaultVal": null,
                "required": false,
                "sdfProperty": "Lot Corp Name"
            },
            {
                "dbProperty": "Lot Number",
                "defaultVal": null,
                "required": false,
                "sdfProperty": "Lot Number"
            },
            {
                "dbProperty": "Parent Stereo Category",
                "defaultVal": null,
                "required": false,
                "sdfProperty": "Parent Stereo Category"
            },
            {
                "dbProperty": "Parent Stereo Comment",
                "defaultVal": null,
                "required": false,
                "sdfProperty": "Parent Stereo Comment"
            },
            {
                "dbProperty": "Lot Chemist",
                "defaultVal": null,
                "required": false,
                "sdfProperty": "Lot Chemist"
            }
        ]
    :param object: The object to convert which must have an as_dict method
    :return: The mapping array of dictionaries which creates a compound registration mapping
    """
    # Convert object to dictionary
    object_dict = object.as_dict()

    # For each of the keys in the object, reate an object of the form:
    # "dbProperty": "Lot Amount Units",
    # "defaultVal": null,
    # "required": false,
    # "sdfProperty": "Lot Amount Units"

    # Get the keys of the object
    keys = object_dict.keys()

    # Create the mapping
    mapping = []
    for key in keys:
        mapping.append({
            "dbProperty": key.replace('_', ' ').title(),
            "defaultVal": None,
            "required": False,
            "sdfProperty": key.replace('_', ' ').title()
        })

    return mapping
