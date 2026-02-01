"""
Story creation prompts and safety validation.

This module contains prompts for original story generation with comprehensive
safety guardrails to prevent inappropriate content and copyright violations.
"""

import re
from typing import List, Tuple


# =============================================================================
# COPYRIGHT BLOCKLIST
# =============================================================================

COPYRIGHTED_CHARACTERS = [
    # Disney - Classic
    "mickey mouse", "minnie mouse", "donald duck", "daisy duck",
    "goofy", "pluto", "chip and dale", "chip", "dale",

    # Disney - Princesses
    "elsa", "anna", "frozen", "olaf", "kristoff",
    "moana", "maui",
    "ariel", "little mermaid", "sebastian", "flounder",
    "belle", "beauty and the beast", "beast", "gaston",
    "cinderella", "prince charming",
    "rapunzel", "tangled", "flynn rider",
    "tiana", "princess and the frog",
    "mulan", "mushu",
    "jasmine", "aladdin", "genie", "jafar",
    "snow white", "seven dwarfs",
    "aurora", "sleeping beauty", "maleficent",
    "pocahontas", "meeko",
    "merida", "brave",

    # Disney - Movies
    "simba", "lion king", "mufasa", "scar", "timon", "pumbaa",
    "nemo", "finding nemo", "dory", "marlin",
    "woody", "buzz lightyear", "toy story", "jessie",
    "lightning mcqueen", "cars", "mater",
    "sulley", "mike wazowski", "monsters inc",
    "wall-e", "eve",
    "ratatouille", "remy", "linguini",
    "incredibles", "mr incredible", "elastigirl",
    "stitch", "lilo",
    "bambi", "thumper",
    "dumbo",
    "pinocchio", "jiminy cricket",
    "peter pan", "tinker bell", "captain hook",
    "winnie the pooh", "pooh", "tigger", "piglet", "eeyore",
    "alice in wonderland", "mad hatter", "cheshire cat",

    # Marvel
    "spider-man", "spiderman", "peter parker",
    "iron man", "tony stark",
    "captain america", "steve rogers",
    "hulk", "bruce banner",
    "thor", "loki",
    "black widow", "natasha romanoff",
    "hawkeye",
    "black panther", "t'challa", "wakanda",
    "doctor strange", "stephen strange",
    "ant-man", "scott lang",
    "captain marvel", "carol danvers",
    "wolverine", "logan",
    "deadpool",
    "thanos",
    "avengers",
    "x-men",

    # DC Comics
    "batman", "bruce wayne", "dark knight",
    "superman", "clark kent", "kal-el",
    "wonder woman", "diana prince",
    "flash", "barry allen",
    "aquaman", "arthur curry",
    "green lantern",
    "joker", "harley quinn",
    "robin", "nightwing",
    "justice league",

    # Pokemon
    "pokemon", "pikachu", "charizard", "mewtwo",
    "bulbasaur", "squirtle", "charmander",
    "ash ketchum", "misty", "brock",

    # Paw Patrol
    "paw patrol", "ryder", "chase", "marshall",
    "skye", "rubble", "rocky", "zuma", "everest",

    # Other Popular Characters
    "peppa pig", "george pig",
    "bluey", "bingo",
    "daniel tiger",
    "curious george",
    "clifford", "big red dog",
    "dora the explorer", "dora", "boots",
    "thomas the tank engine", "thomas",
    "bob the builder",
    "barney",

    # Gaming
    "sonic", "sonic the hedgehog", "tails", "knuckles",
    "mario", "luigi", "princess peach", "bowser",
    "kirby",
    "pac-man",
    "donkey kong",
    "link", "zelda",

    # Star Wars
    "star wars", "luke skywalker", "darth vader",
    "yoda", "obi-wan", "han solo", "chewbacca",
    "princess leia", "r2-d2", "c-3po",
    "kylo ren", "rey",

    # Harry Potter
    "harry potter", "hermione", "ron weasley",
    "dumbledore", "voldemort", "hagrid",
    "hogwarts",

    # Transformers
    "transformers", "optimus prime", "bumblebee",
    "megatron",

    # TMNT
    "teenage mutant ninja turtles", "tmnt",
    "leonardo", "michelangelo", "donatello", "raphael",

    # Sesame Street
    "sesame street", "elmo", "big bird", "cookie monster",
    "oscar the grouch", "bert", "ernie",

    # Looney Tunes
    "bugs bunny", "daffy duck", "tweety bird",
    "sylvester", "porky pig", "road runner", "wile e coyote",

    # Others
    "snoopy", "charlie brown", "peanuts",
    "garfield", "odie",
    "scooby-doo", "shaggy",
    "spongebob", "patrick star",
]


# =============================================================================
# INAPPROPRIATE KEYWORDS
# =============================================================================

INAPPROPRIATE_KEYWORDS = [
    # Violence
    "kill", "murder", "blood", "gore", "stab", "shoot", "gun",
    "weapon", "knife", "sword", "bomb", "explosion", "war",
    "fight", "punch", "kick", "hit", "hurt", "wound", "injury",
    "dead", "death", "die", "dying",

    # Scary/Horror
    "scary", "horror", "terrifying", "frightening", "nightmare",
    "demon", "devil", "ghost", "zombie", "vampire",
    "creepy", "spooky",

    # Inappropriate Content
    "sex", "sexual", "porn", "nude", "naked",
    "drug", "cocaine", "marijuana", "heroin",
    "alcohol", "beer", "wine", "drunk",
    "cigarette", "smoking", "tobacco",

    # Profanity (basic list)
    "damn", "hell", "crap", "shit", "fuck",
    "ass", "bastard", "bitch",

    # Negative Themes
    "suicide", "abuse", "kidnap", "torture",
    "evil", "wicked", "vicious",
]


# =============================================================================
# STORY CREATION PROMPT TEMPLATE
# =============================================================================

STORY_CREATION_PROMPT_TEMPLATE = """You are a children's book author specializing in stories for ages {age_min}-{age_max}.

CRITICAL SAFETY REQUIREMENTS:
You MUST follow these rules strictly. Violations will result in the story being rejected.

1. **Age Appropriateness**: Content must be suitable for {age_min}-{age_max} year olds
   - No violence, fighting, or physical harm
   - No scary creatures, monsters, or frightening situations
   - No references to death, injury, or danger
   - No weapons of any kind

2. **Positive Values Only**:
   - Stories should teach kindness, friendship, sharing, and cooperation
   - Characters should solve problems through communication and creativity
   - No bullying, teasing, or meanness between characters
   - Conflicts should be gentle and easily resolved

3. **No Inappropriate Content**:
   - No references to drugs, alcohol, or smoking
   - No adult themes or relationships
   - No bathroom humor beyond what's developmentally appropriate
   - No profanity or rude language

4. **Copyright Compliance**:
   - DO NOT use any copyrighted characters (Disney, Marvel, Pixar, etc.)
   - Create ORIGINAL characters with unique names
   - Avoid any recognizable franchise elements or settings
   - If the user's prompt mentions copyrighted characters, CREATE NEW ORIGINAL CHARACTERS INSTEAD

5. **Refusal Protocol**:
   - If the user's prompt asks for inappropriate content, politely refuse
   - Respond with: "I cannot create that story as it contains [reason]. Would you like me to create a similar but age-appropriate story about [alternative]?"

---

STORY REQUIREMENTS:

TARGET AUDIENCE: {age_min}-{age_max} years old
LANGUAGE: {language}
TONE: {tone} (cheerful, calm, adventurous, or silly)
LENGTH: {length} pages (short=6-8, medium=10-12, long=14-16)

STRUCTURE:
1. First line: Story title (simple, engaging, 2-6 words)
2. Following lines: One sentence per line (these become book pages)
3. Each sentence: 5-10 words, simple vocabulary
4. Story arc: Setup → Simple problem → Easy resolution → Happy ending
5. Use repetition and rhythm to make it engaging for young children

STYLE GUIDELINES:
- Use present tense for immediacy ("Max jumps in the puddle")
- Include sensory details children can relate to (colors, sounds, feelings)
- Add opportunities for interaction (counting, sounds, actions)
- Keep vocabulary at age level: {age_min}-year-olds know ~200-1000 words
- Use rhyming sparingly (only if it flows naturally)

---

USER'S STORY PROMPT:
{user_prompt}

---

YOUR TASK:
Generate an original, safe, engaging story based on the user's prompt. If the prompt is inappropriate or contains copyrighted characters, follow the refusal protocol above.

OUTPUT FORMAT (title on first line, one sentence per line after):"""


# =============================================================================
# REFUSAL DETECTION
# =============================================================================

REFUSAL_PATTERNS = [
    "i cannot create that story",
    "inappropriate content",
    "not suitable for children",
    "copyrighted character",
    "i cannot write",
    "i can't create",
    "unable to generate",
]


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def check_copyrighted_content(prompt: str) -> Tuple[bool, List[str]]:
    """
    Check if the prompt contains copyrighted character names.

    Args:
        prompt: User's story prompt

    Returns:
        Tuple of (has_violation, list of found characters)
    """
    prompt_lower = prompt.lower()
    found_characters = []

    for character in COPYRIGHTED_CHARACTERS:
        # Use word boundaries to avoid false positives
        # e.g., "spider" shouldn't match "spider-man"
        pattern = r'\b' + re.escape(character) + r'\b'
        if re.search(pattern, prompt_lower):
            found_characters.append(character)

    return (len(found_characters) > 0, found_characters)


def check_inappropriate_keywords(prompt: str) -> Tuple[bool, List[str]]:
    """
    Check if the prompt contains inappropriate keywords.

    Args:
        prompt: User's story prompt

    Returns:
        Tuple of (has_violation, list of found keywords)
    """
    prompt_lower = prompt.lower()
    found_keywords = []

    for keyword in INAPPROPRIATE_KEYWORDS:
        # Use word boundaries to avoid false positives
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, prompt_lower):
            found_keywords.append(keyword)

    return (len(found_keywords) > 0, found_keywords)


def is_refusal_response(story: str) -> bool:
    """
    Check if the LLM response is a refusal.

    Args:
        story: Generated story text

    Returns:
        True if the response is a refusal
    """
    story_lower = story.lower()

    for pattern in REFUSAL_PATTERNS:
        if pattern in story_lower:
            return True

    return False


# =============================================================================
# PROMPT BUILDING
# =============================================================================

# Map length to target page count
LENGTH_TO_PAGES = {
    "short": (6, 8),
    "medium": (10, 12),
    "long": (14, 16),
}


def build_story_creation_prompt(
    user_prompt: str,
    age_min: int,
    age_max: int,
    tone: str,
    length: str,
    language: str
) -> str:
    """
    Build the complete prompt for story creation.

    Args:
        user_prompt: User's story idea/prompt
        age_min: Minimum target age
        age_max: Maximum target age
        tone: Story tone (cheerful, calm, adventurous, silly)
        length: Story length (short, medium, long)
        language: Target language

    Returns:
        Formatted prompt string
    """
    # Get page count range for length
    min_pages, max_pages = LENGTH_TO_PAGES.get(length, (10, 12))
    length_description = f"{length} ({min_pages}-{max_pages} pages)"

    return STORY_CREATION_PROMPT_TEMPLATE.format(
        user_prompt=user_prompt,
        age_min=age_min,
        age_max=age_max,
        tone=tone,
        length=length_description,
        language=language
    )
