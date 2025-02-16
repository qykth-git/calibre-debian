#!/usr/bin/env python


__license__   = 'GPL v3'
__copyright__ = '2012, Kovid Goyal <kovid at kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

# cff_standard_strings {{{
# The 391 Standard Strings as used in the CFF format.
# from Adobe Technical None #5176, version 1.0, 18 March 1998

cff_standard_strings = [
'.notdef', 'space', 'exclam', 'quotedbl', 'numbersign', 'dollar', 'percent',
'ampersand', 'quoteright', 'parenleft', 'parenright', 'asterisk', 'plus',
'comma', 'hyphen', 'period', 'slash', 'zero', 'one', 'two', 'three', 'four',
'five', 'six', 'seven', 'eight', 'nine', 'colon', 'semicolon', 'less', 'equal',
'greater', 'question', 'at', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J',
'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
'bracketleft', 'backslash', 'bracketright', 'asciicircum', 'underscore',
'quoteleft', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', 'braceleft',
'bar', 'braceright', 'asciitilde', 'exclamdown', 'cent', 'sterling',
'fraction', 'yen', 'florin', 'section', 'currency', 'quotesingle',
'quotedblleft', 'guillemotleft', 'guilsinglleft', 'guilsinglright', 'fi', 'fl',
'endash', 'dagger', 'daggerdbl', 'periodcentered', 'paragraph', 'bullet',
'quotesinglbase', 'quotedblbase', 'quotedblright', 'guillemotright',
'ellipsis', 'perthousand', 'questiondown', 'grave', 'acute', 'circumflex',
'tilde', 'macron', 'breve', 'dotaccent', 'dieresis', 'ring', 'cedilla',
'hungarumlaut', 'ogonek', 'caron', 'emdash', 'AE', 'ordfeminine', 'Lslash',
'Oslash', 'OE', 'ordmasculine', 'ae', 'dotlessi', 'lslash', 'oslash', 'oe',
'germandbls', 'onesuperior', 'logicalnot', 'mu', 'trademark', 'Eth', 'onehalf',
'plusminus', 'Thorn', 'onequarter', 'divide', 'brokenbar', 'degree', 'thorn',
'threequarters', 'twosuperior', 'registered', 'minus', 'eth', 'multiply',
'threesuperior', 'copyright', 'Aacute', 'Acircumflex', 'Adieresis', 'Agrave',
'Aring', 'Atilde', 'Ccedilla', 'Eacute', 'Ecircumflex', 'Edieresis', 'Egrave',
'Iacute', 'Icircumflex', 'Idieresis', 'Igrave', 'Ntilde', 'Oacute',
'Ocircumflex', 'Odieresis', 'Ograve', 'Otilde', 'Scaron', 'Uacute',
'Ucircumflex', 'Udieresis', 'Ugrave', 'Yacute', 'Ydieresis', 'Zcaron',
'aacute', 'acircumflex', 'adieresis', 'agrave', 'aring', 'atilde', 'ccedilla',
'eacute', 'ecircumflex', 'edieresis', 'egrave', 'iacute', 'icircumflex',
'idieresis', 'igrave', 'ntilde', 'oacute', 'ocircumflex', 'odieresis',
'ograve', 'otilde', 'scaron', 'uacute', 'ucircumflex', 'udieresis', 'ugrave',
'yacute', 'ydieresis', 'zcaron', 'exclamsmall', 'Hungarumlautsmall',
'dollaroldstyle', 'dollarsuperior', 'ampersandsmall', 'Acutesmall',
'parenleftsuperior', 'parenrightsuperior', 'twodotenleader', 'onedotenleader',
'zerooldstyle', 'oneoldstyle', 'twooldstyle', 'threeoldstyle', 'fouroldstyle',
'fiveoldstyle', 'sixoldstyle', 'sevenoldstyle', 'eightoldstyle',
'nineoldstyle', 'commasuperior', 'threequartersemdash', 'periodsuperior',
'questionsmall', 'asuperior', 'bsuperior', 'centsuperior', 'dsuperior',
'esuperior', 'isuperior', 'lsuperior', 'msuperior', 'nsuperior', 'osuperior',
'rsuperior', 'ssuperior', 'tsuperior', 'ff', 'ffi', 'ffl', 'parenleftinferior',
'parenrightinferior', 'Circumflexsmall', 'hyphensuperior', 'Gravesmall',
'Asmall', 'Bsmall', 'Csmall', 'Dsmall', 'Esmall', 'Fsmall', 'Gsmall', 'Hsmall',
'Ismall', 'Jsmall', 'Ksmall', 'Lsmall', 'Msmall', 'Nsmall', 'Osmall', 'Psmall',
'Qsmall', 'Rsmall', 'Ssmall', 'Tsmall', 'Usmall', 'Vsmall', 'Wsmall', 'Xsmall',
'Ysmall', 'Zsmall', 'colonmonetary', 'onefitted', 'rupiah', 'Tildesmall',
'exclamdownsmall', 'centoldstyle', 'Lslashsmall', 'Scaronsmall', 'Zcaronsmall',
'Dieresissmall', 'Brevesmall', 'Caronsmall', 'Dotaccentsmall', 'Macronsmall',
'figuredash', 'hypheninferior', 'Ogoneksmall', 'Ringsmall', 'Cedillasmall',
'questiondownsmall', 'oneeighth', 'threeeighths', 'fiveeighths',
'seveneighths', 'onethird', 'twothirds', 'zerosuperior', 'foursuperior',
'fivesuperior', 'sixsuperior', 'sevensuperior', 'eightsuperior',
'ninesuperior', 'zeroinferior', 'oneinferior', 'twoinferior', 'threeinferior',
'fourinferior', 'fiveinferior', 'sixinferior', 'seveninferior',
'eightinferior', 'nineinferior', 'centinferior', 'dollarinferior',
'periodinferior', 'commainferior', 'Agravesmall', 'Aacutesmall',
'Acircumflexsmall', 'Atildesmall', 'Adieresissmall', 'Aringsmall', 'AEsmall',
'Ccedillasmall', 'Egravesmall', 'Eacutesmall', 'Ecircumflexsmall',
'Edieresissmall', 'Igravesmall', 'Iacutesmall', 'Icircumflexsmall',
'Idieresissmall', 'Ethsmall', 'Ntildesmall', 'Ogravesmall', 'Oacutesmall',
'Ocircumflexsmall', 'Otildesmall', 'Odieresissmall', 'OEsmall', 'Oslashsmall',
'Ugravesmall', 'Uacutesmall', 'Ucircumflexsmall', 'Udieresissmall',
'Yacutesmall', 'Thornsmall', 'Ydieresissmall', '001.000', '001.001', '001.002',
'001.003', 'Black', 'Bold', 'Book', 'Light', 'Medium', 'Regular', 'Roman',
'Semibold'
]
# }}}

STANDARD_CHARSETS = [  # {{{
# ISOAdobe
('.notdef', 'space', 'exclam', 'quotedbl', 'numbersign', 'dollar',
    'percent', 'ampersand', 'quoteright', 'parenleft', 'parenright',
    'asterisk', 'plus', 'comma', 'hyphen', 'period', 'slash', 'zero',
    'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
    'colon', 'semicolon', 'less', 'equal', 'greater', 'question', 'at',
    'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
    'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
    'bracketleft', 'backslash', 'bracketright', 'asciicircum',
    'underscore', 'quoteleft', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i',
    'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w',
    'x', 'y', 'z', 'braceleft', 'bar', 'braceright', 'asciitilde',
    'exclamdown', 'cent', 'sterling', 'fraction', 'yen', 'florin',
    'section', 'currency', 'quotesingle', 'quotedblleft', 'guillemotleft',
    'guilsinglleft', 'guilsinglright', 'fi', 'fl', 'endash', 'dagger',
    'daggerdbl', 'periodcentered', 'paragraph', 'bullet', 'quotesinglbase',
    'quotedblbase', 'quotedblright', 'guillemotright', 'ellipsis',
    'perthousand', 'questiondown', 'grave', 'acute', 'circumflex', 'tilde',
    'macron', 'breve', 'dotaccent', 'dieresis', 'ring', 'cedilla',
    'hungarumlaut', 'ogonek', 'caron', 'emdash', 'AE', 'ordfeminine',
    'Lslash', 'Oslash', 'OE', 'ordmasculine', 'ae', 'dotlessi', 'lslash',
    'oslash', 'oe', 'germandbls', 'onesuperior', 'logicalnot', 'mu',
    'trademark', 'Eth', 'onehalf', 'plusminus', 'Thorn', 'onequarter',
    'divide', 'brokenbar', 'degree', 'thorn', 'threequarters',
    'twosuperior', 'registered', 'minus', 'eth', 'multiply',
    'threesuperior', 'copyright', 'Aacute', 'Acircumflex', 'Adieresis',
    'Agrave', 'Aring', 'Atilde', 'Ccedilla', 'Eacute', 'Ecircumflex',
    'Edieresis', 'Egrave', 'Iacute', 'Icircumflex', 'Idieresis', 'Igrave',
    'Ntilde', 'Oacute', 'Ocircumflex', 'Odieresis', 'Ograve', 'Otilde',
    'Scaron', 'Uacute', 'Ucircumflex', 'Udieresis', 'Ugrave', 'Yacute',
    'Ydieresis', 'Zcaron', 'aacute', 'acircumflex', 'adieresis', 'agrave',
    'aring', 'atilde', 'ccedilla', 'eacute', 'ecircumflex', 'edieresis',
    'egrave', 'iacute', 'icircumflex', 'idieresis', 'igrave', 'ntilde',
    'oacute', 'ocircumflex', 'odieresis', 'ograve', 'otilde', 'scaron',
    'uacute', 'ucircumflex', 'udieresis', 'ugrave', 'yacute', 'ydieresis',
    'zcaron'),

# Expert
('notdef', 'space', 'exclamsmall', 'Hungarumlautsmall', 'dollaroldstyle',
    'dollarsuperior', 'ampersandsmall', 'Acutesmall', 'parenleftsuperior',
    'parenrightsuperior', 'twodotenleader', 'onedotenleader', 'comma',
    'hyphen', 'period', 'fraction', 'zerooldstyle', 'oneoldstyle',
    'twooldstyle', 'threeoldstyle', 'fouroldstyle', 'fiveoldstyle',
    'sixoldstyle', 'sevenoldstyle', 'eightoldstyle', 'nineoldstyle',
    'colon', 'semicolon', 'commasuperior', 'threequartersemdash',
    'periodsuperior', 'questionsmall', 'asuperior', 'bsuperior',
    'centsuperior', 'dsuperior', 'esuperior', 'isuperior', 'lsuperior',
    'msuperior', 'nsuperior', 'osuperior', 'rsuperior', 'ssuperior',
    'tsuperior', 'ff', 'fi', 'fl', 'ffi', 'ffl', 'parenleftinferior',
    'parenrightinferior', 'Circumflexsmall', 'hyphensuperior',
    'Gravesmall', 'Asmall', 'Bsmall', 'Csmall', 'Dsmall', 'Esmall',
    'Fsmall', 'Gsmall', 'Hsmall', 'Ismall', 'Jsmall', 'Ksmall', 'Lsmall',
    'Msmall', 'Nsmall', 'Osmall', 'Psmall', 'Qsmall', 'Rsmall', 'Ssmall',
    'Tsmall', 'Usmall', 'Vsmall', 'Wsmall', 'Xsmall', 'Ysmall', 'Zsmall',
    'colonmonetary', 'onefitted', 'rupiah', 'Tildesmall',
    'exclamdownsmall', 'centoldstyle', 'Lslashsmall', 'Scaronsmall',
    'Zcaronsmall', 'Dieresissmall', 'Brevesmall', 'Caronsmall',
    'Dotaccentsmall', 'Macronsmall', 'figuredash', 'hypheninferior',
    'Ogoneksmall', 'Ringsmall', 'Cedillasmall', 'onequarter', 'onehalf',
    'threequarters', 'questiondownsmall', 'oneeighth', 'threeeighths',
    'fiveeighths', 'seveneighths', 'onethird', 'twothirds', 'zerosuperior',
    'onesuperior', 'twosuperior', 'threesuperior', 'foursuperior',
    'fivesuperior', 'sixsuperior', 'sevensuperior', 'eightsuperior',
    'ninesuperior', 'zeroinferior', 'oneinferior', 'twoinferior',
    'threeinferior', 'fourinferior', 'fiveinferior', 'sixinferior',
    'seveninferior', 'eightinferior', 'nineinferior', 'centinferior',
    'dollarinferior', 'periodinferior', 'commainferior', 'Agravesmall',
    'Aacutesmall', 'Acircumflexsmall', 'Atildesmall', 'Adieresissmall',
    'Aringsmall', 'AEsmall', 'Ccedillasmall', 'Egravesmall', 'Eacutesmall',
    'Ecircumflexsmall', 'Edieresissmall', 'Igravesmall', 'Iacutesmall',
    'Icircumflexsmall', 'Idieresissmall', 'Ethsmall', 'Ntildesmall',
    'Ogravesmall', 'Oacutesmall', 'Ocircumflexsmall', 'Otildesmall',
    'Odieresissmall', 'OEsmall', 'Oslashsmall', 'Ugravesmall',
    'Uacutesmall', 'Ucircumflexsmall', 'Udieresissmall', 'Yacutesmall',
    'Thornsmall', 'Ydieresissmall'),

# Expert Subset
('.notdef', 'space', 'dollaroldstyle', 'dollarsuperior',
        'parenleftsuperior', 'parenrightsuperior', 'twodotenleader',
        'onedotenleader', 'comma', 'hyphen', 'period', 'fraction',
        'zerooldstyle', 'oneoldstyle', 'twooldstyle', 'threeoldstyle',
        'fouroldstyle', 'fiveoldstyle', 'sixoldstyle', 'sevenoldstyle',
        'eightoldstyle', 'nineoldstyle', 'colon', 'semicolon',
        'commasuperior', 'threequartersemdash', 'periodsuperior',
        'asuperior', 'bsuperior', 'centsuperior', 'dsuperior', 'esuperior',
        'isuperior', 'lsuperior', 'msuperior', 'nsuperior', 'osuperior',
        'rsuperior', 'ssuperior', 'tsuperior', 'ff', 'fi', 'fl', 'ffi',
        'ffl', 'parenleftinferior', 'parenrightinferior', 'hyphensuperior',
        'colonmonetary', 'onefitted', 'rupiah', 'centoldstyle',
        'figuredash', 'hypheninferior', 'onequarter', 'onehalf',
        'threequarters', 'oneeighth', 'threeeighths', 'fiveeighths',
        'seveneighths', 'onethird', 'twothirds', 'zerosuperior',
        'onesuperior', 'twosuperior', 'threesuperior', 'foursuperior',
        'fivesuperior', 'sixsuperior', 'sevensuperior', 'eightsuperior',
        'ninesuperior', 'zeroinferior', 'oneinferior', 'twoinferior',
        'threeinferior', 'fourinferior', 'fiveinferior', 'sixinferior',
        'seveninferior', 'eightinferior', 'nineinferior', 'centinferior',
        'dollarinferior', 'periodinferior', 'commainferior'),
]  # }}}
