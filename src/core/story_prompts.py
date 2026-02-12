"""
Story creation prompts and safety validation.

This module contains prompts for original story generation with comprehensive
safety guardrails to prevent inappropriate content and copyright violations.
"""

import json
import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


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

5. **Safety Status**:
   - You MUST set "safety_status" to "safe" if the story is appropriate for the target age group
   - You MUST set "safety_status" to "unsafe" if the user's prompt asks for:
     * Violent, scary, or harmful content
     * Content involving copyrighted characters (Disney, Marvel, etc.)
     * Adult themes, profanity, or age-inappropriate material
     * Any content you would not feel comfortable showing to a young child
   - If "safety_status" is "unsafe":
     * Set "safety_reasoning" to a short, parent-friendly explanation (1-2 sentences) of why the story cannot be created
     * Set "title" to an empty string
     * Set "pages" to an empty array
   - If "safety_status" is "safe":
     * Set "safety_reasoning" to an empty string
     * Generate the full story as normal

---

STORY REQUIREMENTS:

TARGET AUDIENCE: {age_min}-{age_max} years old
LANGUAGE: {language}
TONE: {tone} (cheerful, calm, adventurous, or silly)
LENGTH: {length} pages (short=6-8, medium=10-12, long=14-16)

STRUCTURE:
1. Title: Simple, engaging, 2-6 words
2. Pages: Each page has 1-2 simple sentences (5-10 words each)
3. Story arc: Setup → Simple problem → Easy resolution → Happy ending
4. Use repetition and rhythm to make it engaging for young children

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
Generate an original, safe, engaging story based on the user's prompt. Always set the safety_status field. If the prompt is inappropriate or contains copyrighted characters, set safety_status to "unsafe" with a clear safety_reasoning, and return empty title and pages.

Return the story as structured JSON with safety_status, safety_reasoning, title, and an array of pages."""


# =============================================================================
# STORY OUTPUT JSON SCHEMA (for OpenRouter Structured Outputs)
# =============================================================================

STORY_OUTPUT_JSON_SCHEMA = {
    "name": "story_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "safety_status": {
                "type": "string",
                "enum": ["safe", "unsafe"],
                "description": "Whether the generated story is safe for children. Set to 'unsafe' if the prompt asks for inappropriate, violent, or copyrighted content."
            },
            "safety_reasoning": {
                "type": "string",
                "description": "If safety_status is 'unsafe', a short explanation of why. If 'safe', set to an empty string."
            },
            "title": {
                "type": "string",
                "description": "The story title, simple and engaging, 2-6 words"
            },
            "pages": {
                "type": "array",
                "description": "Ordered list of story pages. If safety_status is 'unsafe', return an empty array.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text content for this page. 1-2 simple sentences."
                        }
                    },
                    "required": ["text"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["safety_status", "safety_reasoning", "title", "pages"],
        "additionalProperties": False
    }
}


def get_story_creation_response_format() -> dict:
    """
    Get the response_format parameter for structured story outputs.

    Returns:
        Dict with type and json_schema for OpenRouter API
    """
    return {
        "type": "json_schema",
        "json_schema": STORY_OUTPUT_JSON_SCHEMA
    }


def parse_story_output_response(response_text: str) -> dict:
    """
    Parse the LLM response into a story dict.

    Args:
        response_text: Raw text response from LLM (should be valid JSON with structured outputs)

    Returns:
        Dict with "safety_status", "safety_reasoning", "title", and "pages", or empty structure on failure
    """
    empty = {"title": "", "pages": [], "safety_status": "safe", "safety_reasoning": ""}

    try:
        text = response_text.strip()

        # Try direct JSON parse first (structured outputs)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: extract JSON from potential markdown wrapping
            json_match = re.search(r'\{[\s\S]*\}', text)
            if not json_match:
                logger.error("Could not find JSON in story response")
                return empty
            data = json.loads(json_match.group())

        # Validate structure
        if not isinstance(data, dict):
            logger.error("Story response is not a JSON object")
            return empty

        safety_status = data.get("safety_status", "safe")
        safety_reasoning = data.get("safety_reasoning", "")
        title = data.get("title", "")
        pages = data.get("pages", [])

        if not isinstance(pages, list):
            logger.error("Story response 'pages' is not an array")
            return empty

        # Normalize pages
        normalized_pages = []
        for page in pages:
            if isinstance(page, dict) and "text" in page:
                normalized_pages.append({"text": str(page["text"])})

        return {
            "safety_status": str(safety_status),
            "safety_reasoning": str(safety_reasoning),
            "title": str(title),
            "pages": normalized_pages,
        }

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Failed to parse story output: {e}")
        return empty


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
