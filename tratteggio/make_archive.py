"""Write the studio's conservation archive into ./archive as Markdown.

Everything here is fictional: the Lanaioli Chapel (the wool guild's chapel) in
an imagined Florentine church, its 1460s fresco of St Michael weighing souls,
and the records a conservation studio would keep about it. Three kinds of trap
are planted: a superseded 1952 condition report, records from a different
chapel with the same subject, and catalogue wording that differs from how a
restorer would phrase a question.
"""
from pathlib import Path

R = {}

R["contract-1462"] = """---
id: contract-1462
title: Commission contract, 1462
chapel: lanaioli
kind: contract
dated: 1462
---
# Commission contract, 1462

## Parties
The Arte della Lana, the wool guild, commissions the painter Jacopo di Neri to paint the east wall of its chapel in fresco, to be finished within two years.

## Subject
Above, St Michael weighing souls, with two angels. Below, at the centre, a wool merchant at his counting table, as an example of honest trade. To the left, the guild consuls kneeling.

## Materials
Ultramarine is to be used only for the mantle of the Virgin in the upper corner. The sky and other blues are to be azurite. Haloes are to be gilded with gold leaf.

## Payment
The guild will pay 90 florins: 40 at the start, 30 when the upper register is approved, and 20 on completion.
"""

R["disegno-14"] = """---
id: disegno-14
title: Disegno 14, study for the merchant
chapel: lanaioli
kind: drawing
dated: 1462
---
# Disegno 14, study for the merchant

## Catalogue entry
Charcoal heightened with white on blue paper, 41 by 28 cm. Preparatory study for the wool merchant in the lower register of the Lanaioli Chapel fresco.

## Description
The merchant is seated, facing left, with a balance held up in his right hand and an open ledger on the table before him. A small dog lies at his feet. Squaring lines show the drawing was transferred to the wall.

## Notes
The coins on the table are only indicated, not counted. The merchant wears a hooded cap with a long tail over his shoulder.
"""

R["disegno-15"] = """---
id: disegno-15
title: Disegno 15, study for the angels
chapel: lanaioli
kind: drawing
dated: 1462
---
# Disegno 15, study for the angels

## Catalogue entry
Metalpoint on prepared paper, 22 by 30 cm. Two angels flanking St Michael in the upper register.

## Description
The left angel holds a trumpet; the right angel points down toward the merchant. Wings are drawn with long, separated feathers.
"""

R["photo-1931"] = """---
id: photo-1931
title: Photograph 1931, lower register
chapel: lanaioli
kind: photograph
dated: 1931
---
# Photograph 1931, lower register

## Catalogue entry
Gelatin silver print, 24 by 30 cm, taken for the city's photographic survey before the 1930s roof repairs.

## What it shows
The lower centre is intact. The merchant sits at his counting table with the balance raised, coins stacked in three piles, and the ledger open. The dog is visible but its head is already damaged.

## Limits
The print is black and white, so it records shapes and tones but not colours.
"""

R["survey-2019"] = """---
id: survey-2019
title: Condition survey, 2019
chapel: lanaioli
kind: condition
dated: 2019
supersedes: report-1952
---
# Condition survey, 2019

## Losses
The main lacuna is in the lower centre and measures 38 by 41 cm. It removes the merchant's head, his right hand and most of the table top.

## Flaking
Paint is lifting along the vertical crack at the right edge of the lower register. Lifting paint must be consolidated before any cleaning.

## Salts
Efflorescence of sulphate salts appears below 1.2 metres, caused by rising damp.

## Earlier treatment
The wax applied in 1953 has darkened and trapped dirt. It should be removed with solvent gels.
"""

R["report-1952"] = """---
id: report-1952
title: Condition report, 1952
chapel: lanaioli
kind: condition
dated: 1952
superseded_by: survey-2019
---
# Condition report, 1952

## Losses
A small loss of about 12 cm in the lower centre, near the merchant's hand.

## Recommendation
Consolidate the whole lower register with a beeswax and resin mixture.
"""

R["treatment-1953"] = """---
id: treatment-1953
title: Treatment record, 1953
chapel: lanaioli
kind: treatment
dated: 1953
---
# Treatment record, 1953

## Work done
The lower register was consolidated with beeswax and resin applied warm. The loss near the merchant's hand was filled with gesso and left unpainted.

## Materials
Beeswax and dammar resin, ratio 3 to 1.
"""

R["infrared-2020"] = """---
id: infrared-2020
title: Infrared and raking-light study, 2020
chapel: lanaioli
kind: imaging
dated: 2020
---
# Infrared and raking-light study, 2020

## Underdrawing
Infrared reflectography shows the sinopia under the merchant. In the underdrawing his head first turned right, toward the angels, and was changed to face left during painting.

## Giornate
Raking light shows 23 giornate, the day-sized patches of fresh plaster. The merchant was painted in a single giornata.
"""

R["pigments-2020"] = """---
id: pigments-2020
title: Pigment analysis, 2020
chapel: lanaioli
kind: analysis
dated: 2020
---
# Pigment analysis, 2020

## Blues
X-ray fluorescence found azurite in the sky. Ultramarine was found only in the Virgin's mantle, as the contract required.

## Reds
The merchant's robe is vermilion glazed with a red lake. The red lake has faded in areas exposed to light.

## Gold
Gold leaf in the haloes was laid on a mordant, not on fresh plaster.
"""

R["ledger-1463"] = """---
id: ledger-1463
title: Guild payment ledger, 1463
chapel: lanaioli
kind: ledger
dated: 1463
---
# Guild payment ledger, 1463

## Payments to the painter
Jacopo di Neri received 30 florins in March 1463 after the consuls approved the upper register.

## Purchases
The guild paid separately for 2 ounces of ultramarine, bought from the Gesuati friars.
"""

R["inventory-1789"] = """---
id: inventory-1789
title: Church inventory, 1789
chapel: lanaioli
kind: inventory
dated: 1789
---
# Church inventory, 1789

## Entry
The wool guild chapel has an old painting on the wall of St Michael and a merchant, much spoiled by damp in the lower part.
"""

R["studio-rules"] = """---
id: studio-rules
title: Studio rules for retouching
chapel: studio
kind: policy
dated: 2018
---
# Studio rules for retouching

## Losses with evidence
Where a photograph, drawing or copy documents what was lost, reconstruct it in tratteggio, fine vertical hatching that is visible up close.

## Losses without evidence
Where nothing documents the lost area, fill it with a neutral tone. Do not invent forms.

## Reversibility
All retouching must use reversible materials, such as watercolour or conservation-grade resin paints, never oil.
"""

R["environment-2021"] = """---
id: environment-2021
title: Chapel environment monitoring, 2021
chapel: lanaioli
kind: monitoring
dated: 2021
---
# Chapel environment monitoring, 2021

## Humidity
Relative humidity in the chapel ranged from 55 to 72 percent over the year, peaking in November.

## Visitors
Candles near the wall raise surface temperature. The studio recommends moving the candle stand at least 3 metres away.
"""

# A different chapel with the same subject: the wrong chapel.
R["pistoia-survey"] = """---
id: pistoia-survey
title: Condition survey, San Michele chapel, Pistoia
chapel: pistoia
kind: condition
dated: 2017
---
# Condition survey, San Michele chapel, Pistoia

## Losses
A lacuna of 60 by 55 cm in the lower register removes the merchant's torso and the coins.

## Subject
St Michael weighing souls above a merchant holding a purse.
"""

R["pistoia-drawing"] = """---
id: pistoia-drawing
title: Drawing for the Pistoia merchant
chapel: pistoia
kind: drawing
dated: 1470
---
# Drawing for the Pistoia merchant

## Description
Pen and brown ink. The merchant stands, facing right, holding a purse in his left hand. No balance appears.
"""


def main(out: Path = Path(__file__).parent / "archive") -> None:
    out.mkdir(exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()
    for slug, text in R.items():
        (out / f"{slug}.md").write_text(text.strip() + "\n", encoding="utf-8")
    print(f"wrote {len(R)} records to {out}")


if __name__ == "__main__":
    main()
