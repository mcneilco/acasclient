from acasclient.lsthing import (CodeValue, SimpleLsThing, LsThing, clob, ACAS_DDICT, ACAS_AUTHOR)

from datetime import datetime

# Constants
ACAS_LSTHING = 'ACAS LsThing'
META_DATA = 'protocol metadata'
LS_TYPE = 'default'
LS_KIND = 'default'
PREFERRED_LABEL = 'protocol name'
STATUS = 'protocol status'
NOTEBOOK_PAGE = 'notebook page'
PROJECT = 'project'
COMMENTS = 'comments'
ASSAY_TREE_RULE = 'assay tree rule'
PROTOCOL_STATUS = 'protocol status'
ASSAY_STAGE = 'assay stage'
SCIENTIST = 'scientist'
ASSAY_PRINCIPLE = 'assay principle'
CREATION_DATE = 'creation date'
PROTOCOL_DETAILS = 'protocol details'
NOTEBOOK = 'notebook'


class Protocol(SimpleLsThing):
    ls_type = LS_TYPE
    ls_kind = LS_KIND
    preferred_label_kind = PREFERRED_LABEL

    def __init__(self, name=None, scientist=None, recorded_by=None, assay_principle=None, assay_stage='unassigned', creation_date=None, protocol_details=None,
                 notebook=None, comments=None, assay_tree_rule=None, protocol_status='created', notebook_page=None, project='unassigned', ls_thing=None):
        names = {PREFERRED_LABEL: name}

        if not creation_date:
            creation_date = datetime.now()

        metadata = {
            META_DATA: {
                ASSAY_PRINCIPLE: clob(assay_principle),
                ASSAY_STAGE: CodeValue(assay_stage, 'assay', 'stage', ACAS_DDICT),
                SCIENTIST: CodeValue(scientist, 'assay', 'scientist', ACAS_AUTHOR),
                CREATION_DATE: creation_date,
                PROTOCOL_DETAILS: clob(protocol_details),
                NOTEBOOK: notebook,
                COMMENTS: clob(comments),
                ASSAY_TREE_RULE: assay_tree_rule,
                PROTOCOL_STATUS: CodeValue(protocol_status, 'protocol', 'status', ACAS_DDICT),
                NOTEBOOK_PAGE: notebook_page,
                PROJECT: CodeValue(project, 'project', 'biology', ACAS_DDICT)
            }
        }
        super(Protocol, self).__init__(ls_type=self.ls_type, ls_kind=self.ls_kind, names=names, recorded_by=recorded_by,
                                       preferred_label_kind=self.preferred_label_kind, metadata=metadata, ls_thing=ls_thing)

    def save(self, client, skip_validation=False):
        """Persist changes to the ACAS server.

        :param client: Authenticated instances of acasclient.client
        :type client: acasclient.client
        """
        # Run validation
        if not skip_validation:
            self.validate(client)
        self._prepare_for_save(client)
        # Persist
        protocol_dict = self._ls_thing.as_camel_dict()
        resp_dict = client.save_protocol(protocol_dict)
        self._ls_thing = LsThing.from_camel_dict(resp_dict)
        self._cleanup_after_save()
        return self
