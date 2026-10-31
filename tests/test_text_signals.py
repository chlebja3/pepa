from pathlib import Path
import sys
import unittest

# the modules sit in helper/ in the release and at the top of the development tree
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'helper'), str(ROOT)]

from text_signals import find, with_signals


class TextSignalsTest(unittest.TestCase):
    def test_scam_tactics(self):
        text = 'Váš účet bude zablokován. Převeďte peníze na nový bezpečný účet a nainstalujte AnyDesk.'
        self.assertEqual([sid for sid, _ in find(text)], ['safe_account', 'remote_access', 'pressure'])

    def test_plain_message_unchanged(self):
        text = 'Ahoj, v sobotu přijedeme na oběd, vezmu koláč.'
        self.assertEqual(with_signals(text), text)

    def test_hint_appended(self):
        self.assertIn('[Automatické signály: ', with_signals('Výhra na vás čeká, vyzvedněte si ji.'))


if __name__ == '__main__':
    unittest.main()
