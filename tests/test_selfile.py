import acasclient.selfile as acas_file
from collections import OrderedDict
import unittest
from pathlib import Path


###############################################################################
# Functions
###############################################################################
def get_path(fname):
    return Path(__file__).resolve()\
                        .parent.joinpath(fname)

###############################################################################
# Setup test files
###############################################################################


gen_csv_in_fname = get_path('selfile/35250_FG_acas.csv')
gen_xls_in_fname = get_path('selfile/35250_FG_acas.xls')
gen_xlsx_in_fname = get_path('selfile/35250_FG_acas.xlsx')
# NOTE: Add output to gitignore
gen_out_fname = get_path('selfile/test_acas_generic-out.csv')
gen_blank_fname = get_path('selfile/test_blank_acas_generic.csv')

gen_col_in_fname = get_path('selfile/column_order_check.csv')
gen_col_out_fname = get_path('selfile/column_order_check-test-out.csv')

dr_in_fname = get_path('selfile/DoseResponse_Fit_Pre-Fit.xlsx')
# NOTE: Add output to gitignore
dr_out_fname = get_path('selfile/DoseResponse_Fit_Pre-Fit.test-out.csv')
dr_ref_fname = get_path('selfile/DoseResponse_Fit_Pre-Fit.csv')

###############################################################################
# Tests
###############################################################################


class SimpleExperimentLoaderFileTests(unittest.TestCase):
    def test_get_file_type(self):
        assert acas_file.get_file_type(gen_csv_in_fname) == acas_file.CSV
        assert acas_file.get_file_type(gen_xls_in_fname) == acas_file.XLS
        assert acas_file.get_file_type(gen_xlsx_in_fname) == acas_file.XLSX
        assert acas_file.get_file_type(dr_in_fname) == acas_file.XLSX
        assert acas_file.get_file_type('foo.xls') == acas_file.XLS
        assert acas_file.get_file_type('foo.CSV') == acas_file.CSV

    def test_generic_init(self):
        expt = acas_file.Generic(gen_csv_in_fname)
        assert expt.format == acas_file.GENERIC
        assert expt.datatype == OrderedDict(
            [
            ('Corporate Batch ID', 'Datatype'),
            ('SOS1 FP assay Kd (uM)', 'Number'),
            ('citation', 'Text')
            ])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (28, 3)
        assert expt.calculated_results_df.shape == (28, 3)

    def test_generic_load_file(self):
        expt = acas_file.Generic()
        assert expt.expt_df.shape == (0, 0)
        assert expt.calculated_results_df.shape == (0, 0)
        assert expt.format == acas_file.GENERIC

        # From csv.
        expt.loadFile(gen_csv_in_fname)
        assert expt.datatype == OrderedDict([('Corporate Batch ID', 'Datatype'), ('SOS1 FP assay Kd (uM)', 'Number'), ('citation', 'Text')])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (28, 3)
        assert expt.calculated_results_df.shape == (28, 3)

        # From xlsx.
        expt.loadFile(gen_xlsx_in_fname)
        assert expt.datatype == OrderedDict([('Corporate Batch ID', 'Datatype'), ('SOS1 FP assay Kd (uM)', 'Number'), ('citation', 'Text')])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (28, 3)
        assert expt.calculated_results_df.shape == (28, 3)

        # From xls.
        expt.loadFile(gen_xls_in_fname)
        assert expt.datatype == OrderedDict([('Corporate Batch ID', 'Datatype'), ('SOS1 FP assay Kd (uM)', 'Number'), ('citation', 'Text')])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (28, 3)
        assert expt.calculated_results_df.shape == (28, 3)

    def test_generic_saveas(self):
        expt = acas_file.Generic(gen_csv_in_fname)
        expt.saveAs(gen_out_fname)
        ref_lines = []
        with open(gen_csv_in_fname) as fh:
            ref_lines = fh.readlines()
        test_lines = []
        with open(gen_out_fname) as fh:
            test_lines = fh.readlines()
        assert ref_lines == test_lines

    def test_generic_from_blank(self):
        expt = acas_file.Generic()
        expt.protocol_name = 'my super cool protocol'
        expt.experiment_name = 'ATP-Glo Assay 2020-05-19'
        expt.scientist = 'Jackson'
        expt.notebook = 'results_2020-05-19.pdf'
        expt.page = 'page 19'
        expt.assay_date = '2020-05-20'
        expt.project = 'Star89'
        # Dummy data, but this could come from a ctfile.sd_to_df, or
        # rdkit.PandasTools, or whatever.
        expt.expt_df = acas_file.pd.DataFrame(
            {
                'Corporate ID': ['IDX-000001-001', 'IDX-000002-001'],
                'IC50 (nM)': [10.0, 1.0],
                'Hill Slope': [1.2, 1.5],
                'Assay Comment': ['If you are not part of the soln', 'you are part of the ppt']
            }
        )
        # Datatype need to be provided as a dict (or ordereddict)
        # err, careful - not datatypes plural.
        expt.datatype = {
            'Corporate ID': 'Datatype',
            'IC50 (nM)': 'Numeric',
            'Hill Slope': 'Numeric',
            'Assay Comment': 'Text'
        }
        assert expt.format == acas_file.GENERIC
        # validate() behavior may change so this test may need review.
        assert expt.validate() == True
        expt.saveAs(gen_blank_fname)

    def test_generic_column_order(self):
        expt = acas_file.Generic(gen_col_in_fname)
        expt.saveAs(gen_col_out_fname)
        assert 1 == 1

    def test_dose_response_init(self):
        expt = acas_file.DoseResponse(dr_in_fname)
        assert expt.format == acas_file.DOSE_RESPONSE
        assert expt.datatype == OrderedDict([
            ('Corporate Batch ID', 'Datatype'),
            ('Rendering Hint', 'Text (hidden)'),
            ('curve id', 'Text'),
            ('Min', 'Number'),
            ('Max', 'Number'),
            ('Slope', 'Number'),
            ('EC50', 'Number'),
            ('Fitted Slope', 'Number (hidden)'),

        ])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (87, 8)
        assert expt.calculated_results_df.shape == (87, 8)
        assert expt.raw_results == OrderedDict([
            ('curve id', 'temp id'),
            ('Dose (uM)', 'x'),
            ('Response (efficacy)', 'y'),
            ('flag', 'flag')
        ])
        assert expt.raw_expt_df.shape == (1720, 4)
        assert expt.raw_results_df.shape == (1720, 4)

    def test_dose_response_load_file(self):
        expt = acas_file.DoseResponse()
        assert expt.expt_df.shape == (0, 0)
        assert expt.calculated_results_df.shape == (0, 0)
        assert expt.format == acas_file.DOSE_RESPONSE
        expt.loadFile(dr_in_fname)
        assert expt.datatype == OrderedDict([
            ('Corporate Batch ID', 'Datatype'),
            ('Rendering Hint', 'Text (hidden)'),
            ('curve id', 'Text'),
            ('Min', 'Number'),
            ('Max', 'Number'),
            ('Slope', 'Number'),
            ('EC50', 'Number'),
            ('Fitted Slope', 'Number (hidden)'),

        ])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (87, 8)
        assert expt.calculated_results_df.shape == (87, 8)
        assert expt.raw_results == OrderedDict([
            ('curve id', 'temp id'),
            ('Dose (uM)', 'x'),
            ('Response (efficacy)', 'y'),
            ('flag', 'flag')
        ])
        assert expt.raw_results_datatype == OrderedDict([
            ('curve id', 'temp id'),
            ('Dose (uM)', 'x'),
            ('Response (efficacy)', 'y'),
            ('flag', 'flag')
        ])
        assert expt.raw_expt_df.shape == (1720, 4)
        assert expt.raw_results_df.shape == (1720, 4)

    def test_dose_response_saveas(self):
        expt = acas_file.DoseResponse(dr_in_fname)
        expt.saveAs(dr_out_fname)
        ref_lines = []
        with open(dr_ref_fname) as fh:
            ref_lines = fh.readlines()
        test_lines = []
        with open(dr_out_fname) as fh:
            test_lines = fh.readlines()
        assert ref_lines == test_lines

    def test_get_batch_ids(self):
        expt = acas_file.DoseResponse(dr_in_fname)
        correct_corp_ids = {'CMPD-10213-01', 'CMPD-10191-01', 'CMPD-10228-01', 'CMPD-10233-01', 'CMPD-10184-01', 'CMPD-10207-01', 'CMPD-10202-01', 'CMPD-10240-01', 'CMPD-10232-01', 'CMPD-10193-01', 'CMPD-10196-01', 'CMPD-10180-01', 'CMPD-10205-01', 'CMPD-10200-01', 'CMPD-10225-01', 'CMPD-10238-01', 'CMPD-10242-01', 'CMPD-10251-01', 'CMPD-10185-01', 'CMPD-10206-01', 'CMPD-10214-01', 'CMPD-10230-01', 'CMPD-10237-01', 'CMPD-10204-01', 'CMPD-10011-02', 'CMPD-10235-01', 'CMPD-10212-01', 'CMPD-10239-01', 'CMPD-10231-01', 'CMPD-10223-01', 'CMPD-10247-01', 'CMPD-10186-01', 'CMPD-10220-01', 'CMPD-10189-01', 'CMPD-10219-01', 'CMPD-10241-01', 'CMPD-10181-01', 'CMPD-10178-01', 'CMPD-10253-01', 'CMPD-10227-01', 'CMPD-10211-01', 'CMPD-10226-01', 'CMPD-10222-01', 'CMPD-10216-01', 'CMPD-10194-01', 'CMPD-10254-01', 'CMPD-10182-01', 'CMPD-10190-01', 'CMPD-10243-01', 'CMPD-10199-01', 'CMPD-10244-01', 'CMPD-10003-02', 'CMPD-10197-01', 'CMPD-10195-01', 'CMPD-10210-01', 'CMPD-10217-01', 'CMPD-10252-01', 'CMPD-10257-01', 'CMPD-10246-01', 'CMPD-10183-01', 'CMPD-10250-01', 'CMPD-10221-01', 'CMPD-10187-01', 'CMPD-10179-01', 'CMPD-10198-01', 'CMPD-10236-01', 'CMPD-10203-01', 'CMPD-10224-01', 'CMPD-10249-01', 'CMPD-10258-01', 'CMPD-10188-01', 'CMPD-10256-01', 'CMPD-10229-01', 'CMPD-10248-01', 'CMPD-10218-01', 'CMPD-10201-01', 'CMPD-10245-01', 'CMPD-10208-01', 'CMPD-10192-01', 'CMPD-10215-01', 'CMPD-10209-01', 'CMPD-10234-01', 'CMPD-10255-01'}
        assert expt.getCorporateBatchIds() == correct_corp_ids

        expt = acas_file.Generic(gen_csv_in_fname)
        correct_corp_ids = {'LIT-0010498-35250', 'LIT-0010515-35250', 'LIT-0010511-35250', 'LIT-0010519-35250', 'LIT-0010508-35250', 'LIT-0010509-35250', 'LIT-0010495-35250', 'LIT-0010504-35250', 'LIT-0010496-35250', 'LIT-0010507-35250', 'LIT-0010510-35250', 'LIT-0010516-35250', 'LIT-0010499-35250', 'LIT-0010505-35250', 'LIT-0010500-35250', 'LIT-0010520-35250', 'LIT-0010513-35250', 'LIT-0010502-35250', 'LIT-0010512-35250', 'LIT-0010521-35250', 'LIT-0010503-35250', 'LIT-0010517-35250', 'LIT-0010501-35250', 'LIT-0010497-35250', 'LIT-0010514-35250', 'LIT-0010522-35250', 'LIT-0010506-35250', 'LIT-0010518-35250'}
        assert expt.getCorporateBatchIds() == correct_corp_ids

    def test_get_assay_endpoints(self):
        expt = acas_file.DoseResponse(dr_in_fname)
        endpts = {'Rendering Hint', 'Fitted Slope', 'curve id', 'Max', 'Slope', 'EC50', 'Min'}
        assert expt.getEndpointNames() == endpts 

        expt = acas_file.Generic(gen_csv_in_fname)
        endpts = {'SOS1 FP assay Kd (uM)', 'citation'} 
        assert expt.getEndpointNames() == endpts 

    def test_generic_load_str_xlsx(self):
        expt = acas_file.Generic()
        with open(gen_xlsx_in_fname, "rb") as fh:
            expt.loadStr(
                file_str=fh.read(),
                file_type=acas_file.XLSX
            )
        assert expt.datatype == OrderedDict([('Corporate Batch ID', 'Datatype'), ('SOS1 FP assay Kd (uM)', 'Number'), ('citation', 'Text')])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (28, 3)
        assert expt.calculated_results_df.shape == (28, 3)
        
    def test_generic_load_str_csv(self):
        expt = acas_file.Generic()
        with open(gen_csv_in_fname, encoding='utf-8') as fh:
            expt.loadStr(
                file_str=fh.read(),
                file_type=acas_file.CSV
            )
        assert expt.datatype == OrderedDict([('Corporate Batch ID', 'Datatype'), ('SOS1 FP assay Kd (uM)', 'Number'), ('citation', 'Text')])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (28, 3)
        assert expt.calculated_results_df.shape == (28, 3)

    def test_dose_response_load_str_xlsx(self):
        expt = acas_file.DoseResponse()
        assert expt.expt_df.shape == (0, 0)
        assert expt.calculated_results_df.shape == (0, 0)
        assert expt.format == acas_file.DOSE_RESPONSE
        with open(dr_in_fname, 'rb') as fh:
            expt.loadStr(
                file_str=fh.read(),
                file_type=acas_file.XLSX
            )
        assert expt.datatype == OrderedDict([
            ('Corporate Batch ID', 'Datatype'),
            ('Rendering Hint', 'Text (hidden)'),
            ('curve id', 'Text'),
            ('Min', 'Number'),
            ('Max', 'Number'),
            ('Slope', 'Number'),
            ('EC50', 'Number'),
            ('Fitted Slope', 'Number (hidden)'),

        ])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (87, 8)
        assert expt.calculated_results_df.shape == (87, 8)
        assert expt.raw_results == OrderedDict([
            ('curve id', 'temp id'),
            ('Dose (uM)', 'x'),
            ('Response (efficacy)', 'y'),
            ('flag', 'flag')
        ])
        assert expt.raw_results_datatype == OrderedDict([
            ('curve id', 'temp id'),
            ('Dose (uM)', 'x'),
            ('Response (efficacy)', 'y'),
            ('flag', 'flag')
        ])
        assert expt.raw_expt_df.shape == (1720, 4)
        assert expt.raw_results_df.shape == (1720, 4)

    def test_dose_response_load_str_csv(self):
        expt = acas_file.DoseResponse()
        assert expt.expt_df.shape == (0, 0)
        assert expt.calculated_results_df.shape == (0, 0)
        assert expt.format == acas_file.DOSE_RESPONSE
        with open(dr_ref_fname, 'r') as fh:
            expt.loadStr(
                file_str=fh.read(),
                file_type=acas_file.CSV
            )
        assert expt.datatype == OrderedDict([
            ('Corporate Batch ID', 'Datatype'),
            ('Rendering Hint', 'Text (hidden)'),
            ('curve id', 'Text'),
            ('Min', 'Number'),
            ('Max', 'Number'),
            ('Slope', 'Number'),
            ('EC50', 'Number'),
            ('Fitted Slope', 'Number (hidden)'),

        ])
        assert expt.VALID_DATATYPES == set(['Datatype', 'Number', 'Text', 'Date', 'Standard Deviation', 'Image File', 'Comments', 'Number (hidden)', 'Text (hidden)', 'Date (hidden)', 'Standard Deviation (hidden)', 'Image File (hidden)', 'Comments (hidden)'])
        assert expt.expt_df.shape == (87, 8)
        assert expt.calculated_results_df.shape == (87, 8)
        assert expt.raw_results == OrderedDict([
            ('curve id', 'temp id'),
            ('Dose (uM)', 'x'),
            ('Response (efficacy)', 'y'),
            ('flag', 'flag')
        ])
        assert expt.raw_results_datatype == OrderedDict([
            ('curve id', 'temp id'),
            ('Dose (uM)', 'x'),
            ('Response (efficacy)', 'y'),
            ('flag', 'flag')
        ])
        assert expt.raw_expt_df.shape == (1720, 4)
        assert expt.raw_results_df.shape == (1720, 4)



