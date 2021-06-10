""" Interactions in ACAS are directional relationships between two LsThings,
 the "first" LsThing and the "second" LsThing.
 The convention is for the interaction lsType to be a directional verb.
 This helps indicate which LsThing should be the "first" and "second".
 i.e. If we have an LsThing "rock" and an LsThing "scissors",
 we'd use the Interaction "beats" to indicate "rock beats scissors".

 To be able to store the same type of relationship consistently, we must always save
 the "forward" direction of the interaction.
 i.e. If we are saving "rock beats scissors", we should never save "scissors is beaten by rock"
 or "scissors loses to rock".

 To simplify this, lsthing.SimpleLsThing and lsthing.SimpleLink implement ways to add links
 from either direction by specifying a "verb" and a "linked thing". Those implementations reference
 the canonical dictionary of "forward" and "backward" interactions and will do the necessary transforms
 such that only "forward" interactions get saved to ACAS.
"""


INTERACTION_VERBS_DICT = {
    'relates to': 'is related to',
    'references': 'is referenced by',
    'instantiates': 'is instantiated by',
    'contains': 'is contained by',
    'owns': 'is owned by',
    'matches': 'is matched by',
    'comprises': 'is comprised of',
    'analyzes': 'is analyzed by',
    'is input structure for': 'has input structure',
    'owns': 'is owned by'
}


def opposite(verb):
    "Returns the opposite of verb"
    inverse_dict = {value: key for key,
                    value in INTERACTION_VERBS_DICT.items()}
    if verb in INTERACTION_VERBS_DICT:
        return INTERACTION_VERBS_DICT[verb]
    elif verb in inverse_dict:
        return inverse_dict[verb]
    else:
        raise ValueError('Interaction verb {} not recognized.'.format(verb))
