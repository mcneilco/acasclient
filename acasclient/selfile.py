"""
A module to read, edit, and write ACAS 'Single Experiment
Loader' files.

Common formats are supported for both input and output: csv, and
excel


"""
# Contributors:  Shawn Watts


################################################################################
# Packages
################################################################################
import collections
import logging
import io
import os
from functools import partial
import pandas as pd


################################################################################
# Globals/Constants
################################################################################
# File formats/types.
CSV = '.csv'
XLS = '.xls'
XLSX = '.xlsx'
LOT_CORP_NAME = 'Corporate Batch ID'
GENERIC = 'Generic'
DOSE_RESPONSE = 'Dose Response'

# ACAS-CmpdReg constants in sdf files.
PARENT_CORP_NAME = 'Parent Corp Name'
PARENT_STEREO_CAT = 'Parent Stereo Category'
PARENT_ALIASES = 'Parent Aliases'
LOT_NUM = 'Lot Number'
LOT_NOTEBOOK_PAGE = 'Lot Notebook Page'
LOT_CHEMIST = 'Lot Chemist'
LOT_DATE = 'Lot Synthesis Date'
LOT_COMMENTS = 'Lot Comments'
LOT_SUPPLIER = 'Lot Supplier'
LOT_SUPPLIER_ID = 'Lot Supplier ID'
LOT_BARCODE = 'Lot Barcode'
LOT_AMOUNT = 'Lot Amount'
LOT_AMOUNT_UNITS = 'Lot Amount Units'
LOT_PURITY = 'Lot Purity'
LOT_PURITY_MEASURED_BY = 'Lot Purity Measured By'
LOT_SALT_ABBREV = 'Lot Salt Abbrev'
LOT_SALT_EQ = 'Lot Salt Equivalents'
REG_LOT_CORP_NAME = 'Registered Lot Corp Name'
REG_PARENT_CORP_NAME = 'Registered Parent Corp Name'
REG_LOT_AMOUNT = 'Registered Lot Amount'
REG_LOT_AMOUNT_UNITS = 'Registered Lot Amount Units'
REG_PARENT_ALIASES = 'Registered Parent Aliases'
REG_LEVEL = 'Registration Level'


################################################################################
# Logging
################################################################################
logger = logging.getLogger(__name__).addHandler(logging.NullHandler())


################################################################################
# Functions
################################################################################
def get_file_type(file_name):
    """
    :return: The file extension
    :rtype: str

    :param file_name: Path to file to check.
    :type file_name: str

    :note: a guess at the file format based on the extension:  csv, xls, or xlsx.

    :raise: ValueError if the file extension is not recognized.

    """

    try:
        ext = os.path.splitext(file_name)[1].lower()
    except (TypeError, ValueError) as err:
        logger.critical(err)
        raise ValueError(f"Unknown file name extension: {file_name}")

    allowed_extensions = (CSV, XLSX, XLS)
    if ext in allowed_extensions:
        return ext
    else:
        raise ValueError(f"Unknown file type: {file_name}")


def get_read_func_by_file_type(file_type):
    """
    :return: The pandas read_x function
    :rtype: function

    :param file_type: File extension.
    :type file_type: str

    """

    if file_type == CSV:
        read_func = partial(pd.read_csv, dtype=str)
    elif file_type == XLSX:
        read_func = partial(pd.read_excel, engine='openpyxl', dtype=str)
    else:
        read_func = partial(pd.read_excel, dtype=str)
    return read_func


def load_from_str(file_str, file_type):
    """
    'Factory function' for Generic or DoseResponse experiments.

    :param file_str:  Contents of an experiment file to load.
    :type file_str: str

    :param file_type: File extension that indicates the file format.
    :type file_type: Module constant

    """

    expt = Generic()
    expt.loadStr(file_str, file_type)
    if expt.format == GENERIC:
        return expt
    expt = DoseResponse()
    expt.loadStr(file_str, file_type)
    return expt


################################################################################
# Classes
################################################################################
class AbstractExperiment():
    """
    Interface for reading formatted ACAS SEL files.

    """

    META_HEADER = [
        'Experiment Meta Data',
        'Format',
        'Protocol Name',
        'Experiment Name',
        'Scientist',
        'Notebook',
        'Page',
        'Assay Date',
        'Project',
    ]

    RESULTS_HEADER = {
        'Calculated Results': None,
        'Datatype': None
    }

    VALID_DATATYPES = [
        'Datatype', 'Number', 'Text', 'Date',
        'Standard Deviation', 'Image File', 'Comments',
    ]
    VALID_DATATYPES.extend(
        [f'{vdtype} (hidden)' for vdtype in VALID_DATATYPES[1:]]
    )
    VALID_DATATYPES = set(VALID_DATATYPES)

    blank = ""
    _meta_rows = 15  # Scan this many rows for the end of meta/start of payload.

    def __init__(self, file_name=None):
        """
        :param file_name: Path to the ACAS Experiment file to load.
        :type file_name:  str

        """

        self.file_name = file_name

        # These map to the meta fields.
        self._experimental_meta_data = self.blank
        self._format = self.blank
        self._protocol_name = self.blank
        self._experiment_name = self.blank
        self._scientist = self.blank
        self._notebook = self.blank
        self._page = self.blank
        self._assay_date = self.blank
        self._project = self.blank

        # Change tracking vars.
        self._expt_has_changed = None
        self._raw_has_changed = None
        self._meta_has_changed = None
        self._datatype_has_changed = None

        # id of the experiment to track if the experiment has been saved
        self._id = None

        # OrderedDict of 'Datatype', Column keys for type.
        self._datatype = collections.OrderedDict(
            [('Corporate Batch ID', 'Datatype')]
        )

        # Experimental results payload is a data frame.
        self._expt_df = pd.DataFrame()

        # Autoload optional file_name.
        if file_name:
            self.loadFile(file_name)

    def as_dict(self):
        """
        :return: A dictionary representation of the experiment.
        :rtype: dict
        """

        return {
            'file_name': self.file_name,
            'format': self.format,
            'protocol_name': self.protocol_name,
            'experiment_name': self.experiment_name,
            'scientist': self.scientist,
            'notebook': self.notebook,
            'page': self.page,
            'assay_date': self.assay_date,
            'project': self.project,
            'datatype': self.datatype,
            'expt_df': self.expt_df.to_dict(),
        }

    def loadFile(self, file_name):
        """
        :param file_name: Path to the file to load.
        :type file_name: str

        """

        self.file_name = file_name
        self._file_type = get_file_type(file_name)
        read_func = get_read_func_by_file_type(self._file_type)
        self._parse(read_func)

    def loadStr(self, file_str, file_type):
        """
        :param file_str:  Contents of an experiment file to load.
        :type file_str: str

        :param file_type: File extension that indicates the file format.
        :type file_type: Module constant

        """

        self._file_type = file_type
        if type(file_str) == str:
            self.file_name = io.StringIO(file_str)
        else:
            self.file_name = io.BytesIO(file_str)
        read_func = get_read_func_by_file_type(self._file_type)
        self._parse(read_func)

    def saveAs(self, file_name):
        """Save to a file on disk"""
        raise NotImplementedError("Defined by subclass")

    def validate(self):
        """Validate the contents"""
        raise NotImplementedError("Defined by subclass")

    def getCorporateBatchIds(self):
        """Return a set of Lot Corp Names recorded in the experiment"""

        lot_corp_names = set()
        if LOT_CORP_NAME in self.expt_df.columns:
            lot_corp_names.update(self.expt_df[LOT_CORP_NAME].dropna().tolist())
        return lot_corp_names

    def getEndpointNames(self):
        """Return set of Assay-Endpoints recorded in the experiment"""

        endpoint_names = set(self.expt_df.columns.tolist())
        endpoint_names.discard(LOT_CORP_NAME)
        return endpoint_names

    # Meta data property() decorators to flag when the representation
    # is altered.
    @property
    def meta_has_changed(self):
        """Return boolean,  True if the meta data changed after file parsing."""
        return self._meta_has_changed

    @meta_has_changed.setter
    def meta_has_changed(self, value):
        # Only set this if True so subsequent checks that are not changes
        # can't unset.
        if value:
            self._meta_has_changed = value

    @property
    def experimental_meta_data(self):
        """Experimental Meta Data (Meta Data)"""
        return self._experimental_meta_data

    @experimental_meta_data.setter
    def experimental_meta_data(self, value):
        self.meta_has_changed = (value != self._experimental_meta_data)
        self._experimental_meta_data = value

    @property
    def format(self):
        """Format (Meta Data)"""
        return self._format

    @format.setter
    def format(self, value):
        self.meta_has_changed = (value != self._format)
        self._format = value

    @property
    def protocol_name(self):
        """Protocol Name (Meta Data)"""
        return self._protocol_name

    @protocol_name.setter
    def protocol_name(self, value):
        self.meta_has_changed = (value != self._protocol_name)
        self._protocol_name = value

    @property
    def experiment_name(self):
        """Experiment Name (Meta Data)"""
        return self._experiment_name

    @experiment_name.setter
    def experiment_name(self, value):
        self.meta_has_changed = (value != self._experiment_name)
        self._experiment_name = value
    # Alias
    name = experiment_name

    @property
    def scientist(self):
        """Scientist (Meta Data)"""
        return self._scientist

    @scientist.setter
    def scientist(self, value):
        self.meta_has_changed = (value != self._scientist)
        self._scientist = value

    @property
    def notebook(self):
        """Notebook (Meta Data)"""
        return self._notebook

    @notebook.setter
    def notebook(self, value):
        self.meta_has_changed = (value != self._notebook)
        self._notebook = value

    @property
    def page(self):
        """Page (Meta Data)"""
        return self._page

    @page.setter
    def page(self, value):
        self.meta_has_changed = (value != self._page)
        self._page = value

    @property
    def assay_date(self):
        """Assay Date (Meta Data)"""
        return self._assay_date

    @assay_date.setter
    def assay_date(self, value):
        self.meta_has_changed = (value != self._assay_date)
        self._assay_date = value

    @property
    def project(self):
        """Project (Meta Data)"""
        return self._project

    @project.setter
    def project(self, value):
        self.meta_has_changed = (value != self._project)
        self._project = value

    @property
    def id(self):
        """ID to uniquely identify the experiment if it is registered in the database."""
        return self._id
    @id.setter
    def id(self, value):
        self._id = value

    @property
    def expt_df(self):
        """
        pd.DataFrame container for the experimental results data.  Also aliased
        as calculated_results_df
        """
        return self._expt_df.copy()

    @expt_df.setter
    def expt_df(self, new_expt_df):
        self._expt_has_changed = self._expt_df.equals(new_expt_df)
        self._expt_df = new_expt_df

    @property
    def calculated_results_df(self):
        """
        pd.DataFrame container for the 'Calculated Results'.

        :note:  The df.columns are just the 'Corporate Batch ID' and endpoints,
        rows represent the values to register.  See calculated_results_datatype
        for the 'Datatype' mapping of the endpoints to type.

        """
        return self._expt_df.copy()

    @calculated_results_df.setter
    def calculated_results_df(self, new_expt_df):
        self._expt_has_changed = self._expt_df.equals(new_expt_df)
        self._expt_df = new_expt_df

    @property
    def datatype(self):
        """
        OrderedDict {(column1: datatype1), ...)} column name keys for datatype.
        """
        return self._datatype

    @datatype.setter
    def datatype(self, new_dict):
        self._datatype_has_changed = (self._datatype == new_dict)
        self._datatype = new_dict

    @property
    def calculated_results_datatype(self):
        """
        OrderedDict {(column1: datatype1), ...)} column name keys for
        Calculated Results datatype.
        """
        return self._datatype

    @calculated_results_datatype.setter
    def calculated_results_datatype(self, new_dict):
        self._datatype_has_changed = (self._datatype == new_dict)
        self._datatype = new_dict


class Generic(AbstractExperiment):
    """
    Class to represent a Generic ACAS experiment file.

    Logical units (meta data, datatype, and calculated_results) are
    represented as separate data members.  There is some internal
    tracking to detect if the original data content is altered, but
    the datatype changes need to be updated by the caller.

    calculated_results_datatype - Datatype endpoint mapping.
    calculated_results_df - Calculated Results dataframe.

    Common formats are supported for both input and output:  csv,
    and excel

    API examples:
    # Read an existing file, change the 'Project' metadata and save.
    import datateam.fileio.acas as acas
    expt = acas.Generic('35250_FG_acas.csv')
    expt.project = 'Test Project'
    expt.saveAs('35250_FG_modified.xlsx')

    # Change the experimental values and save.
    import pandas as pd
    new_results = pd.read_csv('new_data.csv')
    expt.calculated_results_df = new_results
    expt.saveAs('replaced_data.csv')

    # Create new, completely empty handle, and populate it.
    expt = acas.Generic()
    expt.protocol_name = 'my super cool protocol'
    expt.experiment_name = 'ATP-Glo Assay 2020-05-19'
    expt.scientist = 'Jackson'
    expt.notebook = 'results_2020-05-19.pdf'
    expt.page = 'page 19'
    expt.assay_date = '2020-05-20'
    expt.project = 'Star89'
    # Dummy data, but this could come from a ctfile.sd_to_df, or
    # rdkit.PandasTools, or whatever.
    expt.calculated_results_df = pd.DataFrame(
        {
            'Corporate ID': ['IDX-000001-001', 'IDX-000002-001'],
            'IC50 (nM)': [10.0, 1.0],
            'Hill Slope': [1.2, 1.5],
            'Assay Comment': ['If you are not part of the soln', 'you are part of the ppt']
        }
    )
    # Datatype need to be provided as a dict (or ordereddict)
    expt.calculated_results_datatype = {
        'Corporate ID': 'Datatype',
        'IC50 (nM)': 'Numeric',
        'Hill Slope': 'Numeric',
        'Assay Comment': 'Text'
    }
    expt.saveAs('my_expt.csv')

    """

    def __init__(self, file_name=None):
        """
        :param file_name: Path to the ACAS Generic Experiment file to load.
        :type file_name:  str

        """

        super().__init__(file_name)
        self._format = GENERIC

    def _parse(self, read_func):
        raw_df = read_func(
            self.file_name,
            header=None
        )
        self._parseMeta(raw_df.iloc[0:self._meta_rows, [0, 1]])

        # Slice the 'calculated results'.
        self._expt_df = raw_df.iloc[self.RESULTS_HEADER['Datatype']+1:, :]
        self._expt_df.columns = self._expt_df.iloc[0]
        self._expt_df = self._expt_df.drop(self._expt_df.index[0])

        # Do datatype after determining expt_df so the df.columns can be zipped.
        dt_rows = [self.RESULTS_HEADER['Datatype'], self.RESULTS_HEADER['Datatype']+1]
        datatype = raw_df.iloc[dt_rows, :]
        self._datatype = self._parseDataType(datatype)

        # Change tracking vars.
        self._expt_has_changed = False
        self._meta_has_changed = False
        self._datatype_has_changed = False

    def _parseMeta(self, meta_df):
        meta = collections.OrderedDict([(x, '') for x in self.META_HEADER])
        for idx, row in meta_df.iterrows():
            if row[0] in meta:
                meta[row[0]] = row[1]
            if row[0] in self.RESULTS_HEADER:
                self.RESULTS_HEADER[row[0]] = idx
        self._experimental_meta_data = meta['Experiment Meta Data']
        self._format = meta['Format'].strip()
        self._protocol_name = meta['Protocol Name']
        self._experiment_name = meta['Experiment Name']
        self._scientist = meta['Scientist']
        self._notebook = meta['Notebook']
        self._page = meta['Page']
        self._assay_date = meta['Assay Date']
        self._project = meta['Project']

    def _parseDataType(self, datatype):
        datatype = list(datatype.T.to_dict().values())
        datatype = list(datatype[0].values())
        datatype = collections.OrderedDict(zip(self.expt_df.columns, datatype))
        return datatype

    def saveAs(self, file_name=None, file_type=None):
        """
        :param file_name: Path to output file to save record.
        :type file_name: str
        """

        # Must provide either a file_name or a file_type but not both.
        if file_name and file_type:
            raise ValueError('Must provide either a file_name or a file_type but not both.')

        # If file_name is provided, use it.
        if file_name:
            file_type = get_file_type(file_name)

        # Placeholder for better validation.
        self.validate()

        meta_values = [
            self.experimental_meta_data, self.format, self.protocol_name,
            self.experiment_name, self.scientist, self.notebook, self.page,
            self.assay_date, self.project
        ]
        blanks = [self.blank, self.blank, self.blank]
        # Use zero-based numeric column name for all the logical
        # units so they df.concat() nicely.
        df_meta = pd.DataFrame(
            {
                0: self.META_HEADER+blanks[0:2]+['Calculated Results'],
                1: meta_values+blanks
            }
        )
        df_datatype = pd.DataFrame(
            {
                0: [self.datatype.get(x) for x in self.expt_df.columns],
                1: self.expt_df.columns
            }
        )
        df_expt = self.expt_df
        df_expt.columns = range(0, len(df_expt.columns))

        # Append the components into one output df.
        df_out = pd.concat([df_meta, df_datatype.T], sort=True)
        df_out = pd.concat([df_out, df_expt], ignore_index=True, sort=True)

    
        if file_type == CSV:
            output = df_out.to_csv(file_name, header=None, index=False)
        elif file_type in [XLS, XLSX]:
            if file_name is None:
                # Create excel writer object.
                bio = io.BytesIO()
                file_name = pd.ExcelWriter(bio, engine='openpyxl')
            df_out.to_excel(file_name, header=None, index=False)
            file_name.save()
            output = bio.getvalue()
        else:
            raise ValueError(f'Unknown file type {file_type}')
        return output

    def validate(self):
        """
        Return True if:
            Format is 'Generic'
            expt_df.columns have a valid datatype.

        """
        if self.format != GENERIC:
            msg = f"Verify Format. {self.format} != {GENERIC}"
            logger.warning(msg)
            return False
        if self._datatype_has_changed or self._expt_has_changed:
            missing_datatype = []
            for col in self.expt_df.columns:
                if self.datatype.get(col) not in self.VALID_DATATYPES:
                    missing_datatype.append(col)
            if missing_datatype:
                msg = f"Missing datatype: {missing_datatype}"
                logger.warning(msg)
                return False
        return True


class DoseResponse(AbstractExperiment):
    """
    Class to represent a Dose Response ACAS experiment file, which
    has 'raw results' that describe the 'dose-response' titration
    observations.

    Logical units (meta data, datatype, and calculated_results,
    raw_results and raw_results_datatype) are represented as separate
    data members.  There is some internal tracking to detect if the
    original data content is altered, but the datatype changes need
    to be updated by the caller.  The 'Raw Results' string is treated
    as a dummy/spacer.

    Common formats are supported for both input and output:  csv,
    and excel

    API examples:
    import datateam.fileio.acas as acas
    expt = acas.DoseResponse('DoseResponse_Fit_Pre-Fit.xlsx')
    expt.project = 'Test Project'
    expt.saveAs('DoseResponse_Fit_Pre-Fit-out.csv')

    See Generic for more API examples.

    """

    RESULTS_HEADER = {
        'Calculated Results': None,
        'Datatype': None,
        'Raw Results': None,
    }

    VALID_RESPONSE_TYPES = [
        'Ki Fit',
        '4 parameter D-R',
        '4 parameter D-R IC50',
        '4 parameter D-R IC50/DMax',
        'Michaelis-Menten',
        'Substrate Inhibition',
        'Scatter',
        'Scatter Log-x',
        'Scatter Log-y',
        'Scatter Log-x,y'
    ]

    _datatype = {
        'curve id': 'temp id',
        'Concentration (nM)': 'x',
        'Response': 'y',
        'flag': 'flag'
    }
    _meta_rows = 300  # Scan this many rows for the start of 'raw results'.
    _raw_has_changed = None
    _raw_expt_df = None

    @property
    def raw_expt_df(self):
        """
        pd.DataFrame container for the experimental raw results data.  Also
        aliased as raw_results_df
        """
        return self._raw_expt_df.copy()

    @raw_expt_df.setter
    def raw_expt_df(self, new_raw_expt_df):
        self._raw_expt_has_changed = self._raw_expt_df.equals(new_raw_expt_df)
        self._raw_expt_df = new_raw_expt_df

    @property
    def raw_results_df(self):
        """
        pd.DataFrame container for the experimental Raw Results data.

        :note:  The df.columns are just the 'curve id', 'dose (units)',
        'response' and 'flag', rows represent the values to register.  See
        raw_results_datatype for the 'temp id'  mapping of the endpoints to
        type.

        """
        return self._raw_expt_df.copy()

    @raw_results_df.setter
    def raw_results_df(self, new_raw_expt_df):
        if self._raw_expt_df:
            self._raw_expt_has_changed = self._raw_expt_df.equals(new_raw_expt_df)
            self._raw_expt_df = new_raw_expt_df
        else:
            self._raw_expt_has_changed = True
            self._raw_expt_df = new_raw_expt_df


    @property
    def raw_results(self):
        """OrderedDict {(column1: temp_id1), ...)} column name keys for raw results data."""
        if hasattr(self, '_raw_results'):
            return self._raw_results
        else:
            return self._datatype

    @raw_results.setter
    def raw_results(self, new_dict):
        self._raw_results_has_changed = (self._raw_results == new_dict)
        self._raw_results = new_dict

    @property
    def raw_results_datatype(self):
        """OrderedDict {(column1: temp_id1), ...)} column name keys for raw results data."""
        return self._raw_results

    @raw_results.setter
    def raw_results_datatype(self, new_dict):
        self._raw_results_has_changed = (self._raw_results == new_dict)
        self._raw_results = new_dict

    def __init__(self, file_name=None):
        """
        :param file_name: Path to the ACAS Dose Response Experiment file to load.
        :type file_name:  str

        """

        super().__init__(file_name)
        self._format = DOSE_RESPONSE

    def _parse(self, read_func):
        raw_df = read_func(
            self.file_name,
            header=None,
        )
        self._parseMeta(raw_df.iloc[0:self._meta_rows, [0, 1]])

        # Slice the 'calculated results'.
        self._expt_df = raw_df.iloc[self.RESULTS_HEADER['Datatype']+1:self.RESULTS_HEADER['Raw Results'], :]
        self._expt_df.columns = self._expt_df.iloc[0]
        self._expt_df = self._expt_df.drop(self._expt_df.index[0])
        self._expt_df = self._expt_df.loc[:, self._expt_df.columns.notna()]

        # Do datatype after determining expt_df so the df.columns can be zipped.
        dt_rows = [self.RESULTS_HEADER['Datatype'], self.RESULTS_HEADER['Datatype']+1]
        datatype = raw_df.iloc[dt_rows, :]
        self._datatype = self._parseDataType(datatype)

        # 'Raw results' row is just treated as a spacer and ignored.
        self._raw_expt_df = raw_df.iloc[self.RESULTS_HEADER['Raw Results']+2:, :]
        self._raw_expt_df.columns = self._raw_expt_df.iloc[0]
        self._raw_expt_df = self._raw_expt_df.drop(self._raw_expt_df.index[0])
        self._raw_expt_df = self._raw_expt_df.loc[:, self._raw_expt_df.columns.notna()]

        # Do raw_results after determining raw_expt_df so the
        # df.columns can be zipped.
        rr_rows = [self.RESULTS_HEADER['Raw Results']+1, self.RESULTS_HEADER['Raw Results']+2]
        rr_datatype_df = raw_df.iloc[rr_rows, :]
        rr_datatype_df = rr_datatype_df.fillna('')
        self._raw_results = self._parseRawResultsDataTypes(rr_datatype_df)

        # Change tracking vars.
        self._expt_has_changed = False
        self._raw_has_changed = False
        self._meta_has_changed = False
        self._datatype_has_changed = False

    def _parseMeta(self, meta_df):
        meta = collections.OrderedDict([(x, '') for x in self.META_HEADER])
        for idx, row in meta_df.iterrows():
            if row[0] in meta:
                meta[row[0]] = row[1]
            if row[0] in self.RESULTS_HEADER:
                self.RESULTS_HEADER[row[0]] = idx
        self._experimental_meta_data = meta['Experiment Meta Data']
        self._format = meta['Format'].strip()
        self._protocol_name = meta['Protocol Name']
        self._experiment_name = meta['Experiment Name']
        self._scientist = meta['Scientist']
        self._notebook = meta['Notebook']
        self._page = meta['Page']
        self._assay_date = meta['Assay Date']
        self._project = meta['Project']

    def _parseDataType(self, datatype):
        datatype = list(datatype.T.to_dict().values())
        datatype = list(datatype[0].values())
        datatype = collections.OrderedDict(zip(self.expt_df.columns, datatype))
        return datatype

    def _parseRawResultsDataTypes(self, raw_results):
        raw_results = list(raw_results.T.to_dict().values())
        raw_results = list(raw_results[0].values())
        raw_results = collections.OrderedDict(
            zip(self.raw_expt_df.columns, raw_results)
        )
        return raw_results

    def saveAs(self, file_name=None, file_type=None):
        """
        :param file_name: Path to output file to save record.
        :type file_name: str

        """

        # Must provide either a file_name or a file_type but not both.
        if file_name and file_type:
            raise ValueError('Must provide either a file_name or a file_type but not both.')

        # If file_name is provided, use it.
        if file_name:
            file_type = get_file_type(file_name)

        # Placeholder for better validation.
        self.validate()

        meta_values = [
            self.experimental_meta_data, self.format, self.protocol_name,
            self.experiment_name, self.scientist, self.notebook, self.page,
            self.assay_date, self.project
        ]
        blanks = [self.blank, self.blank, self.blank]
        # Use zero-based numeric column name for all the logical
        # units so they pd.concat() nicely.
        df_meta = pd.DataFrame(
            {
                0: self.META_HEADER+blanks[0:2]+['Calculated Results'],
                1: meta_values+blanks
            }
        )
        df_datatype = pd.DataFrame(
            {
                0: [self.datatype.get(x) for x in self.expt_df.columns],
                1: self.expt_df.columns
            }
        )
        df_expt = self.expt_df
        df_expt.columns = range(0, len(df_expt.columns))

        df_raw_results_header = pd.DataFrame(
            {
                0: ['Raw Results'],
            }
        )
        df_raw_results = pd.DataFrame(
            {
                0: [self.raw_results.get(x) for x in self.raw_expt_df.columns],
                1: self.raw_expt_df.columns
            }
        )
        df_raw_expt = self.raw_expt_df
        df_raw_expt.columns = range(0, len(df_raw_expt.columns))

        # Append the components into one output df.
        df_out = pd.concat([df_meta, df_datatype.T], sort=True)
        df_out = pd.concat([df_out, df_expt], ignore_index=True, sort=True)
        df_out = pd.concat(
            [df_out, df_raw_results_header.T],
            ignore_index=True,
            sort=True
        )
        df_out = pd.concat([df_out, df_raw_results.T], ignore_index=True, sort=True)
        df_out = pd.concat([df_out, df_raw_expt], ignore_index=True, sort=True)
        if file_type == CSV:
            output = df_out.to_csv(file_name, header=None, index=False)
        elif file_type in [XLS, XLSX]:
            if file_name is None:
                # Create excel writer object.
                bio = io.BytesIO()
                file_name = pd.ExcelWriter(bio, engine='openpyxl')
                df_out.to_excel(file_name, header=None, index=False)
                file_name.save()
                output = bio.getvalue()
            else:
                output = df_out.to_excel(file_name, header=None, index=False)
        else:
            raise ValueError(f'Unknown file type {file_type}')
        return output

    def validate(self):
        """
        Return True if:
            Format is 'Dose Response'
            expt_df.columns have a valid datatype.
            TBD
        """
        if self.format != DOSE_RESPONSE:
            msg = f"Verify Format. {self.format} != {DOSE_RESPONSE}"
            logger.warning(msg)
            return False
        if self._datatype_has_changed or self._expt_has_changed:
            missing_datatype = []
            for col in self.expt_df.columns:
                if self.datatype.get(col) not in self.VALID_DATATYPES:
                    missing_datatype.append(col)
            if missing_datatype:
                msg = f"Missing datatype: {missing_datatype}"
                logger.warning(msg)
                return False
        return True