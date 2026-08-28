#!/usr/bin/env python3
"""Apply the source-checked Singapore Oceanarium A-Z animal catalogue."""
import json
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "data/subjects/singapore-oceanarium.json"
BASE = "https://www.singaporeoceanarium.com/en/animals-habitats/animals-a-z"
COMMONS_FALLBACK = {
    "moon-jelly",
    "fried-egg-jelly",
    "horseshoe-crab",
    "napoleon-wrasse",
    "indo-pacific-tarpon",
    "tasmanian-giant-crab",
    "brown-hagfish",
    "coelacanth-replica",
    "dyeing-poison-frog",
}

# id: (official slug, type, natural habitat, Oceanarium exhibit, diet, presentation)
ANIMALS = {
    "american-paddlefish": ("american-paddlefish", "Bony fish", "Freshwater habitats", "Ancient Waters", ["Plankton"], "Live display"),
    "archerfish": ("archerfish", "Bony fish", "Coastal waters", "Singapore's Coast", ["Insects", "Plant matter"], "Live display"),
    "australian-ghostshark": ("australian-ghostshark", "Cartilaginous fish", "Benthic habitats", "Whale Fall & Seamount", ["Molluscs"], "Live display"),
    "australian-lungfish": ("australian-lungfish", "Bony fish", "Freshwater habitats", "Ancient Waters", ["Fish", "Crustaceans", "Frogs"], "Live display"),
    "axolotl": ("axolotl", "Amphibian", "Freshwater habitats", "Conquering Land", ["Crustaceans", "Molluscs", "Fish"], "Live display"),
    "barred-mudskipper": ("barred-mudskipper", "Bony fish", "Intertidal zone", "Singapore's Coast", ["Crustaceans", "Worms"], "Live display"),
    "bluefin-gurnard": ("bluefin-gurnard", "Bony fish", "Benthic habitats", "Whale Fall & Seamount", ["Crustaceans", "Fish", "Molluscs"], "Live display"),
    "bonnethead-shark": ("bonnethead-shark", "Cartilaginous fish", "Coastal waters", "Deep Ocean Exploration", ["Crustaceans", "Molluscs", "Fish"], "Live display"),
    "bowmouth-guitarfish": ("bowmouth-guitarfish", "Cartilaginous fish", "Benthic habitats", "Open Ocean", ["Crustaceans", "Molluscs"], "Live display"),
    "brown-hagfish": ("brown-hagfish", "Jawless fish", "Deep ocean", "Life in the Deep", ["Small invertebrates", "Carrion"], "Preserved specimen"),
    "clown-anemonefish": ("clown-anemonefish", "Bony fish", "Coral reef", "Kelp Forest", ["Plankton"], "Live display"),
    "coelacanth-replica": ("coelacanth-replica", "Bony fish", "Deep ocean", "Ancient Waters", ["Fish", "Cephalopods", "Crustaceans"], "Replica—not a live animal"),
    "deep-sea-spider": ("deep-sea-spider", "Chelicerate", "Deep ocean", "Whale Fall & Seamount", ["Sponges", "Molluscs"], "Live display"),
    "deepsea-lizardfish": ("deepsea-lizardfish", "Bony fish", "Deep ocean", "Life in the Deep", ["Fish"], "Preserved specimen"),
    "dyeing-poison-frog": ("dyeing-poison-frog", "Amphibian", "Terrestrial habitats", "Conquering Land", ["Insects"], "Live display"),
    "epaulette-shark": ("epaulette-shark", "Cartilaginous fish", "Coastal waters", "Ancient Waters", ["Fish", "Crustaceans"], "Live display"),
    "fried-egg-jelly": ("fried-egg-sea-jelly", "Cnidarian", "Open ocean", "Ocean Wonders", ["Plankton"], "Rotating live display"),
    "giant-grouper": ("giant-grouper", "Bony fish", "Coral reef", "Open Ocean", ["Fish", "Crustaceans"], "Live display"),
    "green-humphead-parrotfish": ("green-humphead-parrotfish", "Bony fish", "Coral reef", "Ocean's Future", ["Corals", "Algae"], "Live display"),
    "green-moray": ("green-moray", "Bony fish", "Coral reef", "Benthos", ["Fish", "Crustaceans"], "Live display"),
    "horseshoe-crab": ("indo-pacific-horseshoe-crab", "Chelicerate", "Intertidal zone", "Ancient Waters", ["Detritus", "Molluscs"], "Live display"),
    "leopard-shark": ("indo-pacific-leopard-shark", "Cartilaginous fish", "Coastal waters", "Deep Ocean Exploration", ["Fish", "Crustaceans", "Molluscs"], "Live display"),
    "indo-pacific-tarpon": ("indo-pacific-tarpon", "Bony fish", "Coastal waters", "Open Ocean", ["Fish", "Crustaceans"], "Live display"),
    "knobbly-sea-star": ("knobbly-sea-star", "Echinoderm", "Intertidal zone", "Singapore's Coast", ["Algae", "Molluscs", "Detritus"], "Live display"),
    "long-spined-urchin": ("long-spined-sea-urchin", "Echinoderm", "Coral reef", "Kelp Forest", ["Algae"], "Live display"),
    "longsnout-seahorse": ("longsnout-seahorse", "Bony fish", "Coastal waters", "Reef Animals", ["Crustaceans", "Plankton"], "Live display"),
    "longspine-snipefish": ("longspine-snipefish", "Bony fish", "Benthic habitats", "Whale Fall & Seamount", ["Plankton", "Crustaceans"], "Live display"),
    "moon-jelly": ("moon-jelly", "Cnidarian", "Coastal waters", "Ocean Wonders", ["Plankton"], "Rotating live display"),
    "napoleon-wrasse": ("napoleon-wrasse", "Bony fish", "Coral reef", "Deep Ocean Exploration", ["Fish", "Molluscs", "Crustaceans"], "Live display"),
    "pacific-sea-nettle": ("pacific-sea-nettle", "Cnidarian", "Open ocean", "Ocean Wonders", ["Plankton"], "Rotating live display"),
    "pinecone-soldierfish": ("pinecone-soldierfish", "Bony fish", "Coral reef", "Kelp Forest", ["Plankton"], "Live display"),
    "razorfish": ("razorfish", "Bony fish", "Coastal waters", "Reef Animals", ["Plankton"], "Live display"),
    "red-lionfish": ("red-lionfish", "Bony fish", "Coral reef", "Ocean's Future", ["Fish", "Crustaceans"], "Live display"),
    "reef-manta-ray": ("reef-manta-ray", "Cartilaginous fish", "Coral reef", "Open Ocean", ["Plankton"], "Live display"),
    "sand-tiger-shark": ("sand-tiger-shark", "Cartilaginous fish", "Coastal waters", "Shark Seas", ["Fish", "Cephalopods", "Crustaceans"], "Live display"),
    "scalloped-hammerhead": ("scalloped-hammerhead", "Cartilaginous fish", "Coastal waters", "Shark Seas", ["Fish", "Cephalopods"], "Live display"),
    "spotted-eagle-ray": ("spotted-eagle-ray", "Cartilaginous fish", "Coastal waters", "Open Ocean", ["Molluscs", "Crustaceans", "Fish"], "Live display"),
    "sunflower-sea-star": ("sunflower-sea-star", "Echinoderm", "Benthic habitats", "Whale Fall & Seamount", ["Crustaceans", "Invertebrates"], "Live display"),
    "tasmanian-giant-crab": ("tasmanian-giant-crab", "Crustacean", "Benthic habitats", "Benthos", ["Molluscs", "Carrion"], "Live display"),
    "tawny-nurse-shark": ("tawny-nurse-shark", "Cartilaginous fish", "Benthic habitats", "Shark Seas", ["Fish", "Cephalopods", "Crustaceans"], "Live display"),
    "weedy-seadragon": ("weedy-seadragon", "Bony fish", "Coastal waters", "Reef Animals", ["Crustaceans", "Plankton"], "Live display"),
    "white-spotted-sea-jelly": ("white-spotted-sea-jelly", "Cnidarian", "Coastal waters", "Ocean Wonders", ["Plankton"], "Rotating live display"),
    "bottlenose-dolphin": ("indo-pacific-bottlenose-dolphin", "Mammal", "Coastal waters", "Horizontal Migrators", ["Fish", "Cephalopods"], "Live display"),
}

NEW_NODES = {
    "bluefin-gurnard": ("Bluefin Gurnard", "whale-fall", "Its fan-like blue-edged fins can startle predators and signal to other fish."),
    "bowmouth-guitarfish": ("Bowmouth Guitarfish", "open-ocean", "This critically endangered ray combines a broad ray-like head with a shark-like tail."),
    "brown-hagfish": ("Brown Hagfish", "life-in-deep", "A jawless deep-sea fish that can produce remarkable amounts of defensive slime."),
    "coelacanth-replica": ("Coelacanth (Replica)", "ancient-waters", "A life-sized replica introduces a deep-water lineage once known only from fossils."),
    "deep-sea-spider": ("Deep Sea Spider", "whale-fall", "This marine arthropod breathes through the surface of its long, slender legs."),
    "deepsea-lizardfish": ("Deepsea Lizardfish", "life-in-deep", "A preserved specimen reveals an ambush predator from hundreds to thousands of metres deep."),
    "dyeing-poison-frog": ("Dyeing Poison Frog", "conquering-land", "Its vivid colours warn predators about chemical defences built partly from its wild diet."),
    "pacific-sea-nettle": ("Pacific Sea Nettle", "ocean-wonders", "Long stinging tentacles trail behind a red-brown bell to capture drifting plankton."),
    "reef-manta-ray": ("Reef Manta Ray", "open-ocean", "Wing-like fins carry this huge filter-feeder through clouds of tiny plankton."),
    "sunflower-sea-star": ("Sunflower Sea Star", "whale-fall", "Thousands of tube feet make this many-armed sea star surprisingly fast."),
    "white-spotted-sea-jelly": ("White Spotted Sea Jelly", "ocean-wonders", "Instead of long stinging tentacles, it has spotted bells and many tiny mouths along its oral arms."),
}


def source(slug):
    return {"title": "Singapore Oceanarium — official A–Z animal page", "url": f"{BASE}/{slug}.html"}


def make_node(node_id, title, parent, fact):
    return {
        "id": node_id,
        "keyword": title,
        "summary": fact,
        "key_fact": fact,
        "explainer": "Open the animal profile to compare its body group, natural habitat, Oceanarium story zone and wild diet with neighbouring animals.",
        "why_it_matters": "Seeing an animal in its ecological context makes its shape, movement and survival strategies easier to understand.",
        "wonder": "Which feature would help this animal most in its natural home?",
        "angle_tags": ["habitat", "adaptation", "feeding"],
        "parent": parent,
        "sources": [],
    }


def main():
    data = json.loads(PATH.read_text(encoding="utf-8"))
    by_id = {node["id"]: node for node in data["nodes"]}

    for habitat in (
        {
            "id": "deep-ocean-exploration",
            "keyword": "Deep Ocean Exploration",
            "summary": "Meet deep-water animals through exploration stories and source-checked A–Z profiles.",
            "angle_tags": ["habitat", "adaptation"],
            "parent": "abyss",
            "sources": [{"title": "Singapore Oceanarium — The Abyss", "url": "https://www.singaporeoceanarium.com/en/animals-habitats/the-abyss.html.html.html"}],
        },
        {
            "id": "life-in-deep",
            "keyword": "Life in the Deep",
            "summary": "Preserved specimens make the forms of rarely seen deep-sea animals visible without presenting them as live residents.",
            "angle_tags": ["habitat", "adaptation"],
            "parent": "abyss",
            "sources": [{"title": "Singapore Oceanarium — The Abyss", "url": "https://www.singaporeoceanarium.com/en/animals-habitats/the-abyss.html.html.html"}],
        },
    ):
        if habitat["id"] not in by_id:
            data["nodes"].append(habitat)
            by_id[habitat["id"]] = habitat

    for node_id, (title, parent, fact) in NEW_NODES.items():
        if node_id not in by_id:
            node = make_node(node_id, title, parent, fact)
            data["nodes"].append(node)
            by_id[node_id] = node

    root = by_id["singapore-oceanarium"]
    root["summary"] = "Zoom from six ocean story zones into habitats and all 43 entries in Singapore Oceanarium's official Animals A–Z catalogue."
    root["key_fact"] = "The A–Z catalogue contains 43 source-checked entries, including live displays, rotating displays, preserved specimens and one clearly labelled replica."
    root["explainer"] = "Follow the globe from zone to habitat to animal. Every A–Z profile shows a real photograph, animal type, natural habitat, Oceanarium exhibit and natural diet. Presentation labels prevent replicas and specimens from being mistaken for live residents."

    for node in data["nodes"]:
        node.pop("catalogue", None)
        node.pop("animal", None)

    for node_id, (slug, animal_type, habitat, zone, diet, presentation) in ANIMALS.items():
        node = by_id[node_id]
        node["catalogue"] = "animals-a-z"
        node["animal"] = {
            "type": animal_type,
            "habitat": habitat,
            "zone": zone,
            "diet": diet,
            "presentation": presentation,
        }
        node["visual_query"] = f"{node['keyword']} animal"
        official = source(slug)
        if node_id in COMMONS_FALLBACK:
            node.pop("visual", None)
        else:
            node["visual"] = {
                "src": f"https://s7ap1.scene7.com/is/image/rwsentosa/{slug.replace('-', '_')}:2by1?wid=1200&hei=600&fmt=webp",
                "page": official["url"],
                "alt": f"Official profile photograph of {node['keyword']}",
                "caption": f"{node['keyword']} — official Animals A–Z profile",
                "credit": "Singapore Oceanarium",
                "licence": "Official profile",
            }
        node["sources"] = [official] + [item for item in node.get("sources", []) if item.get("url") != official["url"]]

    # These are natural-history links, not claims about feeding inside the Oceanarium.
    data["edges"] = [edge for edge in data["edges"] if edge.get("type") != "preys-on"]
    data["edges"].extend(
        [
            {
                "from": "tawny-nurse-shark",
                "to": "long-spined-urchin",
                "type": "preys-on",
                "label": "Wild tawny nurse sharks eat sea urchins; this is not an Oceanarium feeding record.",
            },
            {
                "from": "scalloped-hammerhead",
                "to": "spotted-eagle-ray",
                "type": "preys-on",
                "label": "Scalloped hammerheads eat rays; this links an in-catalogue ray example, not a feeding record.",
            },
        ]
    )

    data["content_reviewed"] = "2026-08-28"
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
