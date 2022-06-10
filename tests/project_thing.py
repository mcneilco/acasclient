from acasclient.lsthing import (BlobValue, CodeValue, FileValue, SimpleLsThing)

# Constants
ACAS_DDICT = 'ACAS DDICT'
ACAS_LSTHING = 'ACAS LsThing'
PROJECT_METADATA = 'project metadata'
PROJECT = 'project'
PROJECT_NAME = 'project name'
PROJECT_ALIAS = 'project alias'
STATUS = 'status'
PROJECT_STATUS = 'project status'
PROCEDURE_DOCUMENT = 'procedure document'
PARENT_PROJECT = 'parent project'
BOOLEAN = 'boolean'
IS_RESTRICTED = 'is restricted'
RESTRICTED = 'restricted'
PDF_DOCUMENT = 'pdf document'
START_DATE = 'start date'
NAME_KEY = 'name'
IS_RESTRICTED_KEY = 'is_restricted'
STATUS_KEY = 'status'
START_DATE_KEY = 'start_date'
DESCRIPTION_KEY = 'description'
PDF_DOCUMENT_KEY = 'pdf_document'
PROCEDURE_DOCUMENT_KEY = 'procedure_document'
PARENT_PROJECT_KEY = 'parent_project'
ACTIVE = 'active'
INACTIVE = 'inactive'

class Project(SimpleLsThing):
    ls_type = PROJECT
    ls_kind = PROJECT
    preferred_label_kind = PROJECT_NAME

    def __init__(self, name=None, alias=None, start_date=None, description=None, status=None, is_restricted=True, procedure_document=None, pdf_document=None, recorded_by=None,
                 parent_project=None, ls_thing=None):
        names = {PROJECT_NAME: name, PROJECT_ALIAS: alias}
        metadata = {
            PROJECT_METADATA: {
                START_DATE: start_date,
                DESCRIPTION_KEY: description,
                PROJECT_STATUS: CodeValue(status, PROJECT, STATUS, ACAS_DDICT),
                IS_RESTRICTED: CodeValue(str(is_restricted).lower(), BOOLEAN, BOOLEAN, ACAS_DDICT),
                PROCEDURE_DOCUMENT: BlobValue(file_path=procedure_document),
                PARENT_PROJECT: CodeValue(parent_project, PROJECT, PROJECT, ACAS_LSTHING),
                PDF_DOCUMENT: FileValue(file_path=pdf_document)
            }
        }
        super(Project, self).__init__(ls_type=self.ls_type, ls_kind=self.ls_kind, names=names, recorded_by=recorded_by,
                                      preferred_label_kind=self.preferred_label_kind, metadata=metadata, ls_thing=ls_thing)
