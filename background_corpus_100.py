"""A fresh, fixed corpus for paired animated-background tests."""
import json
from pathlib import Path

GROUPS = {
    'short': '''The lighthouse keeper has returned.
My compass points toward the ruins.
Her gloves are covered in ash.
The elevator stopped between floors.
Our pilot forgot the landing code.
This helmet muffles every sound.
Someone moved the bronze mirror.
The market closes before sunset.
Your lantern attracts those insects.
A familiar voice called from below.
The waterwheel turns against the current.
Our tracker found fresh claw marks.
That robot recognizes your insignia.
The balcony overlooks an empty garden.
His boots leave silver footprints.
The carriage needs a new axle.
My radio receives only static.
The giant appears to be sleeping.
Her portrait conceals a narrow passage.
The desert wind carries distant music.''',
    'story': '''The baker remembered our faces even though we had visited in disguise.
He traded his last pearl for a ticket aboard the departing airship.
We discovered a handwritten invitation inside the damaged mechanical bird.
The dancer kept performing long after the audience had left the hall.
My uncle built this shelter during the first volcanic eruption.
She returned the medal because the victory had cost too many lives.
The astronomer vanished on the evening when both moons turned orange.
I recognized the tune from a lullaby my grandmother used to sing.
Their leader placed a white feather beside each empty bunk.
The diplomat seemed relieved when the meeting ended without an agreement.
We reached the monastery just as its oldest bell cracked in half.
His daughter repaired the watch but kept the mysterious engraving secret.
The rescued sailor described an island absent from every official chart.
She offered us shelter in exchange for a story about the mainland.
The historian hid the original manuscript inside an ordinary recipe book.
Our guide grew nervous whenever the conversation turned to the abandoned station.
The gardener planted roses along the road where his companions disappeared.
I expected an apology, but he handed me a freshly sharpened dagger.
Their final broadcast repeated a set of coordinates nobody could explain.
The young mechanic smiled when the ancient engine finally began to hum.''',
    'action': '''Cover the rear entrance while the miners climb the emergency ladder.
Place the empty lantern on the platform beside the marble basin.
Bring spare cables to the technician working inside the observation dome.
Follow the orange flags through the field of dormant stone giants.
Ask the ferryman to leave enough space for the medical wagon.
Hold the rope steady while I inspect the broken suspension cable.
Gather the scattered documents before the wind carries them into the canal.
Lead the frightened animals away from the malfunctioning defense turret.
Turn the central dial clockwise until the indicator reaches the green mark.
Carry the sealed container upright throughout the journey across the dunes.
Check the lower decks for passengers who missed the evacuation announcement.
Leave a wooden marker wherever the underground trail divides into two paths.
Draw the creature toward the shallow pool beside the ruined amphitheater.
Wait for the patrol boat to pass before swimming across the inlet.
Deliver the replacement lens to the lookout stationed above the canyon.
Use the maintenance hatch to reach the control room beneath the arena.
Help the apprentice arrange the colored stones around the damaged sundial.
Signal the caravan when the final obstacle has been removed.
Collect the fallen branches and reinforce the shelter before the hail arrives.
Read the inscription aloud while I examine the symbols on the ceiling.''',
    'conditions': '''This shield restores 18 energy after blocking 3 consecutive attacks.
If the platform begins shaking, release the handle and crouch immediately.
Only enter the chamber when both pressure gauges display exactly 60.
The drone scans a radius of 14 meters for 8 seconds.
Deliver 5 medical kits before the countdown reaches 01:30.
Do not cross the painted line while the examination lamp is flashing.
Your critical chance increases by 12% while your health remains above 75%.
The special ammunition pierces 2 targets but deals 30% less damage afterward.
You cannot equip this relic until your reputation reaches level 9.
After collecting 11 fragments, return to the excavation supervisor.
If the scanner detects movement, remain still for at least 4 seconds.
The protective field lasts 16 seconds unless its generator is destroyed.
Do not spend the last repair charge before checking the rear engine.
Each rescued worker adds 25 seconds to the remaining evacuation time.
This recipe requires 3 mushrooms, 2 bottles of water, and 1 copper pot.
You may choose another reward only after declining the offered weapon.
The eastern lift remains unavailable until the power conduit is repaired.
Prevent the crawler from losing more than 35% of its armor.
The marked opponent takes 22 additional damage from your next ranged attack.
Do not interrupt the ritual unless the outer circle changes from gold to violet.''',
    'long': '''The curator insists that the damaged painting depicts a real location, although the coastline in the background resembles nothing on our modern maps.
We could follow the smugglers through the caves, but the rising tide would trap anyone who failed to reach the second exit before nightfall.
She accepted the assignment because it offered a chance to find her missing teacher, rather than because she believed the promised reward would ever be paid.
The caretaker asked us to repair the broken fountain before searching the mansion, explaining that its running water kept the restless spirits calm.
Although the new armor protected him from the explosion, its weight prevented him from escaping the flooded compartment without help from the other divers.
I left the package beside the red doorway as instructed, yet the woman who collected it claimed she had expected us to arrive several days earlier.
If you decide to reopen the laboratory, make sure the ventilation system is working before disturbing any of the dust covering the experimental equipment.
The envoy brought a proposal that seemed generous at first, but accepting its final condition would leave the border villages entirely dependent on foreign supplies.
Our scout believes the tracks belong to a wounded animal, though their perfectly even spacing suggests that someone may be trying to lure us into an ambush.
Before activating the beacon, gather everyone inside the reinforced shelter and check that the emergency shutters can still close over the damaged western windows.
The singer recognized the stolen instrument by a tiny scratch near its handle, a detail she had described to the investigators before they found the suspect.
You are free to take the mountain route, provided that you bring enough climbing equipment for the companions who have never crossed an ice field before.
The captain refused to abandon the cargo until we showed him that the cracked containers were leaking a substance capable of dissolving the ships wooden hull.
We assumed the apprentice had misunderstood the instructions, until the master admitted that he had deliberately given her an incomplete version of the spell.
If the creatures remain quiet after the music stops, lower your weapons slowly and allow the youngest one to approach the food placed near the entrance.
The abandoned tram still runs between the two settlements, but nobody knows who repairs its engine or why it always stops at the empty hillside station.
She would have recognized the impostor sooner if the council had allowed her to examine the signature on the treaty instead of keeping it locked away.
The device can locate buried metal objects, but it cannot distinguish valuable artifacts from ordinary scrap without a separate reading from the portable analyzer.
After the storm passes, send a messenger to each neighboring village so that we can learn which roads are safe enough for the supply convoys to use.
We have enough medicine to stabilize the injured passengers tonight, but finding a doctor before morning will require someone to cross the damaged railway bridge.''',
}

CORPUS = [{'id': i + 1, 'group': group, 'text': sentence}
          for i, (group, sentence) in enumerate(
              (group, sentence) for group, block in GROUPS.items() for sentence in block.splitlines())]
assert len(CORPUS) == 100
assert len({row['text'].casefold() for row in CORPUS}) == 100

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    previous = json.loads((root / 'test-results/english-100/corpus.json').read_text(encoding='utf-8'))
    assert not ({r['text'].casefold() for r in CORPUS} & {r['text'].casefold() for r in previous})
    print(json.dumps({'sentences': len(CORPUS), 'repeated_previous_sentences': 0}))
