"""Score proofreading models on a small hand-checked set: python gram_gold.py URL MODEL [--think]

URL is the chat completions endpoint, e.g. http://localhost:8000/v1/chat/completions. Used to choose the model and
mode for proofread.py; it writes no data.
"""
import sys

from proofread import PROMPT, call, parse

BAD = [
    ("Někdo vás vydíruje falešným virusem a chce po vás hned zaplatit peníze za svůj software.", ["vydíruj", "virusem"], ["virem"]),
    ("Někdo se vydává za technickou podporu Microsoftu a snaží se vás zastrašit falešným varováním před virusem.", ["virusem"], ["virem"]),
    ("Tato zpráva vás naláká na rychlé zbohatnutí, což je nebezpečný způsob, jak vás vylákatit na podvod.", ["vylákatit"], []),
    ("Někdo vás vyhrožuje zablokováním účtu a naláká vás na podezřelý odkaz, aby vám ukradl údaje z banky.", ["vás vyhrožuj"], ["vám vyhrožuje"]),
    ("Tato zpráva je běžná dotaz na informace a neobsahuje žádné rizikové požadavky.", ["běžná dotaz"], ["běžný dotaz"]),
    ("Někdo vás neoprávněně zastrašuje časem a chce vás přes podvodný odkaz přimět k kliknutí na nebezpečný web.", ["k kliknutí"], []),
    ("Jedná se o běžnou informaci o vyúčtení, která od vás nevyžaduje žádné nebezpečné kroky ani placení.", ["vyúčtení"], ["vyúčtování"]),
    ("Tato zpráva slibuje nereálně vysokou výhru a vyžaduje, abyste vše drželi v tajnosti, což je typický způsob, jak vás chtějí oklitovat.", ["oklitov"], []),
    ("Tato zpráva vás neoprávněně vyhánějí k rychlé platbě pod pohrůžkou odpojení elektřiny přes podezřelý odkaz.", ["vyhánějí"], []),
    ("Cizí osoba vás vyděřuje nebezpečím pro váš počítač a naléhavě vás nutí k provádění neznámých kroků.", ["vyděřuj"], []),
    ("Banka vás neoprávněně vyhánějí k okamžitému potvrzení údajů přes podezřelý odkaz a vyhrožují vám zablokováním účtu.", ["vyhánějí", "vyhrožují"], []),
    ("Tato zpráva vypadá jako běžná dotaz na prodej věci a neobsahuje nic podezřelého.", ["běžná dotaz"], ["běžný dotaz"]),
]
GOOD = [
    "Neklikejte na odkaz a nic neplaťte. Pokud si chcete ověřit stav své žádosti, kontaktujte svou banku přímo přes jejich oficiální web nebo telefon.",
    "Tato zpráva je pouze běžný článek o koncertu a knihách, který od vás nic nepožaduje.",
    "Tato zpráva je jen běžný dotaz na rady a neobsahuje žádné nebezpečné požadavky.",
    "Neklikejte na odkaz a neplaťte nic. Své platby si raději ověřte přímo u svého operátora nebo v jeho oficiální aplikaci.",
    "Nic neposílejte a žádné osobní údaje neuvádějte, nikdo vám peníze zdarma nedá.",
    "Neklikejte na odkaz a nic neplaťte. Stav zásilky si ověřte přímo ve své aplikaci nebo na oficiálních stránkách dopravce.",
    "Tato zpráva je pouze reklamou na levné inkousty a nevyžaduje žádné nebezpečné kroky.",
    "Jedná se o sdílení informací o projektu a zpráva od vás nic nepožaduje.",
    "Tato zpráva vás pouze informuje o čase doručení zásilky a nevyžaduje žádné rizikové kroky ani platby.",
    "Nic neposílejte a na tuto nabídku nespoléhejte, nikdo nerozdává peníze tak snadno.",
]

url, model, think = sys.argv[1], sys.argv[2], "--think" in sys.argv
fixed = 0
for src, bad, good in BAD:
    out = parse(call(url, model, PROMPT.format(text=src), think))
    ok = not any(b in out for b in bad) and all(g in out for g in good)
    fixed += ok
    print("OK " if ok else "-- ", out)
kept = 0
for src in GOOD:
    out = parse(call(url, model, PROMPT.format(text=src), think))
    kept += out == src
    if out != src:
        print("CHG", out)
print(f"{model}: fixed {fixed}/{len(BAD)}, kept {kept}/{len(GOOD)}")
