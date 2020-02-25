#!/usr/bin/env python

"""Tests for `acasclient` package."""


import unittest
from acasclient import acasclient
from pathlib import Path
import tempfile
import shutil

# SETUP
# "bob" user name registered
# "PROJ-00000001" registered
# CMPD-0000001-001 registered


class TestAcasclient(unittest.TestCase):
    """Tests for `acasclient` package."""

    def setUp(self):
        """Set up test fixtures, if any."""
        creds = acasclient.get_default_credentials()
        self.client = acasclient.client(creds)
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        """Tear down test fixtures, if any."""
        shutil.rmtree(self.tempdir)

    def test_000_creds_from_file(self):
        """Test creds from file."""
        file_credentials = Path(__file__).resolve().\
            parent.joinpath('test_acasclient',
                            'test_000_creds_from_file_credentials')
        creds = acasclient.creds_from_file(
            file_credentials,
            'acas')
        self.assertIn("username", creds)
        self.assertIn("password", creds)
        self.assertIn("url", creds)
        self.assertEqual(creds['username'], 'bob')
        self.assertEqual(creds['password'], 'secret')
        creds = acasclient.creds_from_file(file_credentials,
                                           'different')
        self.assertIn("username", creds)
        self.assertIn("password", creds)
        self.assertIn("url", creds)
        self.assertEqual(creds['username'], 'differentuser')
        self.assertEqual(creds['password'], 'secret')

    def test_001_get_default_credentials(self):
        """Test get default credentials."""
        acasclient.get_default_credentials()

    def test_002_client_initialization(self):
        """Test initializing client."""
        creds = acasclient.get_default_credentials()
        acasclient.client(creds)

    def test_003_projects(self):
        """Test projects."""
        projects = self.client.projects()
        self.assertGreater(len(projects), 0)
        self.assertIn('active', projects[0])
        self.assertIn('code', projects[0])
        self.assertIn('id', projects[0])
        self.assertIn('isRestricted', projects[0])
        self.assertIn('name', projects[0])

    def test_004_upload_files(self):
        """Test upload files."""
        test_003_upload_file_file = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', '1_1_Generic.xlsx')
        files = self.client.upload_files([test_003_upload_file_file])
        self.assertIn('files', files)
        self.assertIn('name', files['files'][0])
        self.assertIn('originalName', files['files'][0])
        self.assertEqual(files['files'][0]["originalName"], '1_1_Generic.xlsx')

    def test_005_register_sdf_request(self):
        """Test register sdf request."""
        test_012_upload_file_file = Path(__file__).resolve().parent\
            .joinpath('test_acasclient', 'test_012_register_sdf.sdf')
        files = self.client.upload_files([test_012_upload_file_file])
        request = {
            "fileName": files['files'][0]["name"],
            "userName": "bob",
            "mappings": [
                {
                    "dbProperty": "Parent Common Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Name"
                },
                {
                    "dbProperty": "Parent Corp Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Corporate ID"
                },
                {
                    "dbProperty": "Lot Amount",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Amount Prepared"
                },
                {
                    "dbProperty": "Lot Amount Units",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Amount Units"
                },
                {
                    "dbProperty": "Lot Color",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Appearance"
                },
                {
                    "dbProperty": "Lot Synthesis Date",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Date Prepared"
                },
                {
                    "dbProperty": "Lot Notebook Page",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Notebook"
                },
                {
                    "dbProperty": "Lot Corp Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Corp Name"
                },
                {
                    "dbProperty": "Lot Number",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Number"
                },
                {
                    "dbProperty": "Lot Purity",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Purity"
                },
                {
                    "dbProperty": "Lot Comments",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Register Comment"
                },
                {
                    "dbProperty": "Lot Chemist",
                    "defaultVal": "bob",
                    "required": True,
                    "sdfProperty": "Lot Scientist"
                },
                {
                    "dbProperty": "Lot Solution Amount",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Solution Amount"
                },
                {
                    "dbProperty": "Lot Solution Amount Units",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Solution Amount Units"
                },
                {
                    "dbProperty": "Lot Supplier",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Source"
                },
                {
                    "dbProperty": "Lot Supplier ID",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Source ID"
                },
                {
                    "dbProperty": "CAS Number",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "CAS"
                },
                {
                    "dbProperty": "Project",
                    "defaultVal": "PROJ-00000001",
                    "required": True,
                    "sdfProperty": "Project Code Name"
                },
                {
                    "dbProperty": "Parent Common Name",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Name"
                },
                {
                    "dbProperty": "Parent Stereo Category",
                    "defaultVal": "unknown",
                    "required": True,
                    "sdfProperty": None
                },
                {
                    "dbProperty": "Parent Stereo Comment",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Structure Comment"
                },
                {
                    "dbProperty": "Lot Is Virtual",
                    "defaultVal": "False",
                    "required": False,
                    "sdfProperty": "Lot Is Virtual"
                },
                {
                    "dbProperty": "Lot Supplier Lot",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Sample ID2"
                },
                {
                    "dbProperty": "Lot Salt Abbrev",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Salt Name"
                },
                {
                    "dbProperty": "Lot Salt Equivalents",
                    "defaultVal": None,
                    "required": False,
                    "sdfProperty": "Lot Salt Equivalents"
                }
            ]

        }
        response = self.client.register_sdf_request(request)
        self.assertIn('reportFiles', response[0])
        self.assertIn('summary', response[0])
        self.assertIn('Registration completed', response[0]['summary'])

    def test_006_register_sdf(self):
        """Test register sdf."""
        test_012_upload_file_file = Path(__file__).resolve().parent.\
            joinpath('test_acasclient', 'test_012_register_sdf.sdf')
        mappings = [
            {
                "dbProperty": "Parent Common Name",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Name"
            },
            {
                "dbProperty": "Parent Corp Name",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Corporate ID"
            },
            {
                "dbProperty": "Lot Amount",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Amount Prepared"
            },
            {
                "dbProperty": "Lot Amount Units",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Amount Units"
            },
            {
                "dbProperty": "Lot Color",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Appearance"
            },
            {
                "dbProperty": "Lot Synthesis Date",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Date Prepared"
            },
            {
                "dbProperty": "Lot Notebook Page",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Notebook"
            },
            {
                "dbProperty": "Lot Corp Name",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Corp Name"
            },
            {
                "dbProperty": "Lot Number",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Number"
            },
            {
                "dbProperty": "Lot Purity",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Purity"
            },
            {
                "dbProperty": "Lot Comments",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Register Comment"
            },
            {
                "dbProperty": "Lot Chemist",
                "defaultVal": "bob",
                "required": True,
                "sdfProperty": "Lot Scientist"
            },
            {
                "dbProperty": "Lot Solution Amount",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Solution Amount"
            },
            {
                "dbProperty": "Lot Solution Amount Units",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Solution Amount Units"
            },
            {
                "dbProperty": "Lot Supplier",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Source"
            },
            {
                "dbProperty": "Lot Supplier ID",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Source ID"
            },
            {
                "dbProperty": "CAS Number",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "CAS"
            },
            {
                "dbProperty": "Project",
                "defaultVal": "PROJ-00000001",
                "required": True,
                "sdfProperty": "Project Code Name"
            },
            {
                "dbProperty": "Parent Common Name",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Name"
            },
            {
                "dbProperty": "Parent Stereo Category",
                "defaultVal": "unknown",
                "required": True,
                "sdfProperty": None
            },
            {
                "dbProperty": "Parent Stereo Comment",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Structure Comment"
            },
            {
                "dbProperty": "Lot Is Virtual",
                "defaultVal": "False",
                "required": False,
                "sdfProperty": "Lot Is Virtual"
            },
            {
                "dbProperty": "Lot Supplier Lot",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Sample ID2"
            },
            {
                "dbProperty": "Lot Salt Abbrev",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Salt Name"
            },
            {
                "dbProperty": "Lot Salt Equivalents",
                "defaultVal": None,
                "required": False,
                "sdfProperty": "Lot Salt Equivalents"
            }
        ]

        response = self.client.register_sdf(test_012_upload_file_file, "bob",
                                            mappings)
        self.assertIn('report_files', response)
        self.assertIn('summary', response)
        self.assertIn('Registration completed', response['summary'])

    def test_007_cmpd_search_request(self):
        """Test cmpd search request."""

        searchRequest = {
            "corpNameList": "",
            "corpNameFrom": "",
            "corpNameTo": "",
            "aliasContSelect": "contains",
            "alias": "",
            "dateFrom": "",
            "dateTo": "",
            "searchType": "substructure",
            "percentSimilarity": 90,
            "chemist": "anyone",
            "maxResults": 100,
            "molStructure": (
                "NSC 1390\n"
                "\n"
                "\n"
                " 10 11  0  0  0  0  0  0  0  0999 V2000\n"
                "   -4.4591   -4.9405    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -2.6905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -7.1905    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -2.9770    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "    0.4473   -4.1905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -4.9405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -5.6905    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -5.4040    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -4.4591   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "  1  8  1  0  0  0  0\n"
                "  1 10  1  0  0  0  0\n"
                "  2 10  2  0  0  0  0\n"
                "  2  6  1  0  0  0  0\n"
                "  3  8  2  0  0  0  0\n"
                "  4  5  1  0  0  0  0\n"
                "  4  6  1  0  0  0  0\n"
                "  5  9  2  0  0  0  0\n"
                "  6  7  2  0  0  0  0\n"
                "  7  8  1  0  0  0  0\n"
                "  7  9  1  0  0  0  0\n"
                "M  END")
        }
        search_results = self.client.\
            cmpd_search_request(searchRequest)
        self.assertGreater(len(search_results["foundCompounds"]), 0)
        self.assertEqual(
            search_results["foundCompounds"][0]["corpName"],
            "CMPD-0000001")

        searchRequest = {
            "molStructure": (
                "NSC 1390\n"
                "\n"
                "\n"
                " 10 11  0  0  0  0  0  0  0  0999 V2000\n"
                "   -4.4591   -4.9405    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -2.6905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -7.1905    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -2.9770    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "    0.4473   -4.1905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -4.9405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -5.6905    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -5.4040    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -4.4591   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "  1  8  1  0  0  0  0\n"
                "  1 10  1  0  0  0  0\n"
                "  2 10  2  0  0  0  0\n"
                "  2  6  1  0  0  0  0\n"
                "  3  8  2  0  0  0  0\n"
                "  4  5  1  0  0  0  0\n"
                "  4  6  1  0  0  0  0\n"
                "  5  9  2  0  0  0  0\n"
                "  6  7  2  0  0  0  0\n"
                "  7  8  1  0  0  0  0\n"
                "  7  9  1  0  0  0  0\n"
                "M  END"),
        }
        search_results = self.client.\
            cmpd_search_request(searchRequest)
        self.assertGreater(len(search_results["foundCompounds"]), 0)
        self.assertEqual(
            search_results["foundCompounds"][0]["corpName"],
            "CMPD-0000001")

    def test_008_cmpd_search(self):
        """Test cmpd search request."""

        molStructure = (
                "NSC 1390\n"
                "\n"
                "\n"
                " 10 11  0  0  0  0  0  0  0  0999 V2000\n"
                "   -4.4591   -4.9405    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -2.6905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -7.1905    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -2.9770    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "    0.4473   -4.1905    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -1.8610   -4.9405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -3.1600   -5.6905    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -0.4344   -5.4040    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "   -4.4591   -3.4405    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
                "  1  8  1  0  0  0  0\n"
                "  1 10  1  0  0  0  0\n"
                "  2 10  2  0  0  0  0\n"
                "  2  6  1  0  0  0  0\n"
                "  3  8  2  0  0  0  0\n"
                "  4  5  1  0  0  0  0\n"
                "  4  6  1  0  0  0  0\n"
                "  5  9  2  0  0  0  0\n"
                "  6  7  2  0  0  0  0\n"
                "  7  8  1  0  0  0  0\n"
                "  7  9  1  0  0  0  0\n"
                "M  END")
        search_results = self.client.\
            cmpd_search(molStructure=molStructure)
        self.assertGreater(len(search_results["foundCompounds"]), 0)
        self.assertEqual(
            search_results["foundCompounds"][0]["corpName"],
            "CMPD-0000001")

    def test_009_export_cmpd_search_results(self):
        """Test export cmpd search results."""
        search_results = {
            "foundCompounds": [
                {
                    "lotIDs": [
                        {
                            "corpName": "CMPD-0000001-001"
                        }
                    ],
                }
            ]
        }
        # Full search results possibilities
        # search_results = {
        #     "foundCompounds": [
        #         {
        #             "corpName": "CMPD-0000001",
        #             "corpNameType": "Parent",
        #             "lotIDs": [
        #                 {
        #                     "buid": 0,
        #                     "corpName": "CMPD-0000001-001",
        #                     "lotNumber": 1,
        #                     "registrationDate": "01/29/2020",
        #                     "synthesisDate": "01/29/2020"
        #                 }
        #             ],
        #             "molStructure": "MOLFILE STRUCTURE"
        #             "parentAliases": [],
        #             "stereoCategoryName": "Achiral",
        #             "stereoComment": ""
        #         }
        #     ],
        #     "lotsWithheld": False
        # }
        search_results_export = self.client.\
            export_cmpd_search_results(search_results)
        self.assertIn('reportFilePath', search_results_export)
        self.assertIn('summary', search_results_export)

    def test_010_export_cmpd_search_results_get_file(self):
        """Test export cmpd search results get file."""
        search_results = {
            "foundCompounds": [
                {
                    "lotIDs": [
                        {
                            "corpName": "CMPD-0000001-001"
                        }
                    ],
                }
            ]
        }
        search_results_export = self.client.\
            export_cmpd_search_results(search_results)
        self.assertIn('reportFilePath', search_results_export)
        self.assertIn('summary', search_results_export)
        search_results_export = self.client.\
            get_file(search_results_export['reportFilePath'])
        print(search_results_export)

    def test_011_get_sdf_file_for_lots(self):
        """Test get sdf file for lots."""
        search_results_export = self.client.\
            get_sdf_file_for_lots(["CMPD-0000001-001"])
        self.assertIn('content', search_results_export)
        content = str(search_results_export['content'])
        self.assertIn('<Parent Corp Name>\\nCMPD-0000001', content)
        self.assertIn('<Lot Corp Name>\\nCMPD-0000001-001', content)
        self.assertIn('<Project>\\nPROJ-00000001', content)
        self.assertIn('<Parent Stereo Category>\\nunknown', content)
        self.assertIn('content-type', search_results_export)
        self.assertIn('name', search_results_export)
        self.assertIn('content-length', search_results_export)
        self.assertIn('last-modified', search_results_export)

    def test_012_write_sdf_file_for_lots(self):
        """Test get sdf file for lots."""
        out_file_path = self.client.\
            write_sdf_file_for_lots(["CMPD-0000001-001"], Path(self.tempdir))
        self.assertTrue(out_file_path.exists())
        out_file_path = self.client\
            .write_sdf_file_for_lots(["CMPD-0000001-001"],
                                     Path(self.tempdir, "output.sdf"))
        self.assertTrue(out_file_path.exists())
        self.assertEqual('output.sdf', out_file_path.name)

    def test_013_experiment_loader_request(self):
        """Test experiment loader request."""
        data_file_to_upload = Path(__file__).\
            resolve().parent.joinpath('test_acasclient', '1_1_Generic.xlsx')
        files = self.client.upload_files([data_file_to_upload])
        request = {"user": "bob",
                   "fileToParse": files['files'][0]["name"],
                   "reportFile": "",
                   "imagesFile": None,
                   "dryRunMode": True}
        response = self.client.experiment_loader_request(request)
        self.assertIn('results', response)
        self.assertIn('errorMessages', response)
        self.assertIn('hasError', response)
        self.assertIn('hasWarning', response)
        self.assertIn('transactionId', response)
        self.assertIsNone(response['transactionId'])
        request = {"user":
                   "bob",
                   "fileToParse": files['files'][0]["name"],
                   "reportFile": "", "imagesFile": None,
                   "dryRunMode": False}
        response = self.client.experiment_loader_request(request)
        self.assertIn('transactionId', response)
        self.assertIsNotNone(response['transactionId'])

    def test_014_experiment_loader(self):
        """Test experiment loader."""
        data_file_to_upload = Path(__file__).resolve()\
            .parent.joinpath('test_acasclient', '1_1_Generic.xlsx')
        response = self.client.\
            experiment_loader(data_file_to_upload, "bob", True)
        self.assertIn('results', response)
        self.assertIn('errorMessages', response)
        self.assertIn('hasError', response)
        self.assertIn('hasWarning', response)
        self.assertIn('transactionId', response)
        self.assertIsNone(response['transactionId'])
        response = self.client.\
            experiment_loader(data_file_to_upload, "bob", False)
        self.assertIn('transactionId', response)
        self.assertIsNotNone(response['transactionId'])

    def test_015_get_protocols_by_label(self):
        """Test get protocols by label"""
        protocols = self.client.get_protocols_by_label("Test Protocol")
        self.assertGreater(len(protocols), 0)
        self.assertIn('codeName', protocols[0])
        self.assertIn('lsLabels', protocols[0])
        self.assertEqual(protocols[0]["lsLabels"][0]["labelText"],
                         "Test Protocol")
        fakeProtocols = self.client.get_protocols_by_label("Fake Protocol")
        self.assertEqual(len(fakeProtocols), 0)

    def test_016_get_experiments_by_protocol_code(self):
        """Test get experiments by protocol code."""
        protocols = self.client.get_protocols_by_label("Test Protocol")
        experiments = self.client.\
            get_experiments_by_protocol_code(protocols[0]["codeName"])
        self.assertGreater(len(experiments), 0)
        self.assertIn('codeName', experiments[0])
        self.assertIn('lsLabels', experiments[0])
        self.assertEqual(experiments[0]["lsLabels"][0]["labelText"],
                         "Test Experiment")

    def test_017_get_experiment_by_code(self):
        """Test get experiment by code."""
        experiment = self.client.get_experiment_by_code("EXPT-00000001")
        self.assertIn('codeName', experiment)
        self.assertIn('lsLabels', experiment)

    def test_018_get_source_file_for_experient_code(self):
        """Test get source file for experiment code."""
        source_file = self.client.\
            get_source_file_for_experient_code("EXPT-00000001")
        self.assertIn('content', source_file)
        self.assertIn('content-type', source_file)
        self.assertIn('name', source_file)
        self.assertIn('content-length', source_file)
        self.assertIn('last-modified', source_file)

    def test_019_write_source_file_for_experient_code(self):
        """Test get source file for experiment code."""
        source_file_path = self.client.\
            write_source_file_for_experient_code("EXPT-00000001", self.tempdir)
        self.assertTrue(source_file_path.exists())
