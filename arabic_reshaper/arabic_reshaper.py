# -*- coding: utf-8 -*-

# This work is licensed under the MIT License.
# To view a copy of this license, visit https://opensource.org/licenses/MIT

# Written by Abdullah Diab (mpcabd)
# Email: mpcabd@gmail.com
# Website: http://mpcabd.xyz

from __future__ import unicode_literals

import re

from itertools import repeat

from .ligatures import LIGATURES
from .reshaper_config import auto_config
from .letters import (UNSHAPED, ISOLATED, TATWEEL, ZWJ, LETTERS_ARABIC,
                      LETTERS_ARABIC_V2, LETTERS_KURDISH, FINAL,
                      INITIAL, MEDIAL, connects_with_letters_before_and_after,
                      connects_with_letter_before, connects_with_letter_after)

HARAKAT_RE = re.compile(
    '['
    '\u0610-\u061a'
    '\u064b-\u065f'
    '\u0670'
    '\u06d6-\u06dc'
    '\u06df-\u06e8'
    '\u06ea-\u06ed'
    '\u08d4-\u08e1'
    '\u08d4-\u08ed'
    '\u08e3-\u08ff'
    ']',

    re.UNICODE | re.X
)


class ArabicReshaper(object):
    """
    A class for Arabic reshaper, it allows for fine-tune configuration over the
    API.

    If no configuration is passed to the constructor, the class will check for
    an environment variable :envvar:`PYTHON_ARABIC_RESHAPER_CONFIGURATION_FILE`
    , if the variable is available, the class will load the file pointed to by
    the variable, and will read it as an ini file.
    If the variable doesn't exist, the class will load with the default
    configuration file :file:`default-config.ini`

    Check these links for information on the configuration files format:

    * Python 3: https://docs.python.org/3/library/configparser.html
    * Python 2: https://docs.python.org/2/library/configparser.html

    See the default configuration file :file:`default-config.ini` for details
    on how to configure your reshaper.
    """

    def __init__(self, configuration=None, configuration_file=None):
        super(ArabicReshaper, self).__init__()

        self.configuration = auto_config(configuration, configuration_file)
        self.language = self.configuration.get('language')

        if self.language == 'ArabicV2':
            self.letters = LETTERS_ARABIC_V2
        elif self.language == 'Kurdish':
            self.letters = LETTERS_KURDISH
        else:
            self.letters = LETTERS_ARABIC

    @property
    def _ligatures_re(self):
        if not hasattr(self, '__ligatures_re'):
            patterns = []
            re_group_index_to_ligature_forms = {}
            index = 0
            FORMS = 1
            MATCH = 0
            for ligature_record in LIGATURES:
                ligature, replacement = ligature_record
                if not self.configuration.getboolean(ligature):
                    continue
                re_group_index_to_ligature_forms[index] = replacement[FORMS]
                patterns.append('({})'.format(replacement[MATCH]))
                index += 1
            self._re_group_index_to_ligature_forms = (
                re_group_index_to_ligature_forms
            )
            self.__ligatures_re = re.compile('|'.join(patterns), re.UNICODE)
        return self.__ligatures_re

    def _get_ligature_forms_from_re_group_index(self, group_index):
        if not hasattr(self, '_re_group_index_to_ligature_forms'):
            return self._ligatures_re
        return self._re_group_index_to_ligature_forms[group_index]

    def reshape(self, text):
        if not text:
            return ''

        output = []

        LETTER = 0
        FORM = 1
        NOT_SUPPORTED = -1

        delete_harakat = self.configuration.getboolean('delete_harakat')
        delete_tatweel = self.configuration.getboolean('delete_tatweel')
        support_zwj = self.configuration.getboolean('support_zwj')
        shift_harakat_position = self.configuration.getboolean(
            'shift_harakat_position'
        )
        use_unshaped_instead_of_isolated = self.configuration.getboolean(
            'use_unshaped_instead_of_isolated'
        )

        positions_harakat = {}

        isolated_form = (UNSHAPED
                         if use_unshaped_instead_of_isolated else ISOLATED)

        for letter in text:
            if HARAKAT_RE.match(letter):
                if not delete_harakat:
                    position = len(output) - 1
                    if shift_harakat_position:
                        position -= 1
                    if position not in positions_harakat:
                        positions_harakat[position] = []
                    if shift_harakat_position:
                        positions_harakat[position].insert(0, letter)
                    else:
                        positions_harakat[position].append(letter)
            elif letter == TATWEEL and delete_tatweel:
                pass
            elif letter == ZWJ and not support_zwj:
                pass
            elif letter not in self.letters:
                output.append((letter, NOT_SUPPORTED))
            elif not output:  # first letter
                output.append((letter, isolated_form))
            else:
                previous_letter = output[-1]
                if previous_letter[FORM] == NOT_SUPPORTED:
                    output.append((letter, isolated_form))
                elif not connects_with_letter_before(letter, self.letters):
                    output.append((letter, isolated_form))
                elif not connects_with_letter_after(
                        previous_letter[LETTER], self.letters):
                    output.append((letter, isolated_form))
                elif (previous_letter[FORM] == FINAL and not
                      connects_with_letters_before_and_after(
                          previous_letter[LETTER], self.letters
                )):
                    output.append((letter, isolated_form))
                elif previous_letter[FORM] == isolated_form:
                    output[-1] = (
                        previous_letter[LETTER],
                        INITIAL
                    )
                    output.append((letter, FINAL))
                # Otherwise, we will change the previous letter to connect
                # to the current letter
                else:
                    output[-1] = (
                        previous_letter[LETTER],
                        MEDIAL
                    )
                    output.append((letter, FINAL))

            # Remove ZWJ if it's the second to last item as it won't be useful
            if support_zwj and len(output) > 1 and output[-2][LETTER] == ZWJ:
                output.pop(len(output) - 2)

        if support_zwj and output and output[-1][LETTER] == ZWJ:
            output.pop()

        if self.configuration.getboolean('support_ligatures'):
            # Clean text from Harakat to be able to find ligatures
            text = HARAKAT_RE.sub('', text)

            # Clean text from Tatweel to find ligatures if delete_tatweel
            if delete_tatweel:
                text = text.replace(TATWEEL, '')

            regex_start = 0
            matchIt = re.finditer(self._ligatures_re, text)
            match = next(matchIt, None)
            while match:
                group_index = next((
                    i for i, group in enumerate(match.groups()) if group
                ), -1)
                forms = self._get_ligature_forms_from_re_group_index(
                    group_index
                )
                a, b = tuple(i+regex_start for i in match.span())
                a_form = output[a][FORM]
                b_form = output[b - 1][FORM]
                ligature_form = None

                # +-----------+----------+---------+---------+----------+
                # | a   \   b | ISOLATED | INITIAL | MEDIAL  | FINAL    |
                # +-----------+----------+---------+---------+----------+
                # | ISOLATED  | ISOLATED | INITIAL | INITIAL | ISOLATED |
                # | INITIAL   | ISOLATED | INITIAL | INITIAL | ISOLATED |
                # | MEDIAL    | FINAL    | MEDIAL  | MEDIAL  | FINAL    |
                # | FINAL     | FINAL    | MEDIAL  | MEDIAL  | FINAL    |
                # +-----------+----------+---------+---------+----------+

                if a_form in (isolated_form, INITIAL):
                    if b_form in (isolated_form, FINAL):
                        ligature_form = ISOLATED
                    else:
                        ligature_form = INITIAL
                else:
                    if b_form in (isolated_form, FINAL):
                        ligature_form = FINAL
                    else:
                        ligature_form = MEDIAL
                if not forms[ligature_form]:
                    regex_start = a+1
                    matchIt = re.finditer(self._ligatures_re, text[regex_start:])
                    match = next(matchIt, None)
                    continue
                output[a] = (forms[ligature_form], NOT_SUPPORTED)
                output[a+1:b] = repeat(('', NOT_SUPPORTED), b - 1 - a)
                match = next(matchIt, None)

        result = []
        if not delete_harakat and -1 in positions_harakat:
            result.extend(positions_harakat[-1])
        for i, o in enumerate(output):
            if o[LETTER]:
                if o[FORM] == NOT_SUPPORTED or o[FORM] == UNSHAPED:
                    result.append(o[LETTER])
                else:
                    result.append(self.letters[o[LETTER]][o[FORM]])

            if not delete_harakat:
                if i in positions_harakat:
                    result.extend(positions_harakat[i])

        return ''.join(result)


default_reshaper = ArabicReshaper()
reshape = default_reshaper.reshape
