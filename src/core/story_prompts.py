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
    # Graphic violence
    "kill", "murder", "blood", "gore", "stab", "shoot", "gun",
    "bomb", "explosion",

    # Horror (genuinely inappropriate for young children)
    "horror", "terrifying", "nightmare",
    "demon", "devil", "zombie", "vampire",

    # Inappropriate content
    "sex", "sexual", "porn", "nude", "naked",
    "drug", "cocaine", "marijuana", "heroin",
    "alcohol", "beer", "wine", "drunk",
    "cigarette", "smoking", "tobacco",

    # Profanity
    "damn", "hell", "crap", "shit", "fuck",
    "ass", "bastard", "bitch",

    # Harmful themes
    "suicide", "abuse", "kidnap", "torture",
]


# =============================================================================
# STORY CREATION PROMPT TEMPLATE
# =============================================================================

STORY_CREATION_PROMPT_TEMPLATE = """You are a children's book author specializing in stories for ages {age_min}-{age_max}.

SAFETY GUIDELINES:
Keep content age-appropriate for {age_min}-{age_max} year olds.

1. **Age-Appropriate Content**:
   - Mild conflict and challenges are fine (getting lost, making a mistake, facing a fear)
   - Friendly creatures, silly monsters, and gentle dragons are welcome
   - Characters can feel scared, sad, frustrated, or make mistakes — that's part of good storytelling
   - Avoid graphic violence, real weapons, or genuinely frightening scenarios
   - No references to drugs, alcohol, adult themes, or profanity

2. **Positive Storytelling**:
   - Stories can include characters who make mistakes and learn from them
   - Mild tension and stakes make stories engaging
   - Conflicts should resolve in age-appropriate ways
   - Characters can be mean or selfish IF the story shows why that behavior is wrong

3. **Copyright Compliance**:
   - DO NOT use any copyrighted characters (Disney, Marvel, Pixar, etc.)
   - Create ORIGINAL characters with unique names
   - If the user's prompt mentions copyrighted characters, CREATE NEW ORIGINAL CHARACTERS with a similar spirit

4. **Safety Status**:
   - Set "safety_status" to "safe" for any age-appropriate story request
   - Set "safety_status" to "unsafe" ONLY if the prompt explicitly asks for:
     * Graphic violence, gore, or truly harmful content
     * Adult/sexual themes or profanity
     * Content that would genuinely distress a young child
   - Copyrighted character requests are NOT "unsafe" — create original alternatives instead
   - If "safety_status" is "unsafe":
     * Set "safety_reasoning" to a short, parent-friendly explanation (1-2 sentences)
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
# STORY VALIDATION PROMPT TEMPLATE
# =============================================================================

STORY_VALIDATION_PROMPT_TEMPLATE = """You are a children's book content reviewer. Your job is to evaluate whether a story is appropriate for children aged {age_min}-{age_max}.

You are NOT writing or rewriting the story. You are ONLY checking if the provided story text is acceptable.

EVALUATION CRITERIA:

1. **Safety**: The story must NOT contain:
   - Graphic violence, gore, or realistic harm
   - Genuinely frightening or disturbing content (nightmares, demons, etc.)
   - References to drugs, alcohol, or smoking
   - Adult/sexual themes or profanity
   - Note: Mild conflict, friendly creatures, characters feeling scared or sad, and characters making mistakes are all FINE

2. **Age Appropriateness**: The story should be broadly suitable for {age_min}-{age_max} year olds:
   - Vocabulary should be mostly understandable for the age group
   - Themes can include challenges, feelings, and learning moments
   - Stories do NOT need to explicitly promote specific values — a simple adventure is fine

3. **Copyright Compliance**: The story must NOT contain:
   - Copyrighted characters (Disney, Marvel, Pixar, DC, Pokemon, etc.)
   - Recognizable franchise elements, settings, or catchphrases

4. **Content Quality**: The story must have:
   - Coherent narrative (not random words or gibberish)
   - At least a basic story structure
   - Meaningful content (not a single repeated phrase)

RULES:
- Set "status" to "pass" if the story is age-appropriate and safe
- Set "status" to "fail" ONLY if the story contains genuinely inappropriate content
- If "fail", set "reasoning" to a short, parent-friendly explanation (1-2 sentences) of what is wrong
- If "pass", set "reasoning" to an empty string
- Be lenient — mild conflict, silly humor, characters feeling scared or sad, and imperfect grammar are all fine
- Focus on catching truly harmful content, not on enforcing a specific storytelling style

---

STORY TITLE: {title}

STORY TEXT:
{story_text}

---

YOUR TASK:
Evaluate the story above. Return your verdict as structured JSON with "status" (pass/fail) and "reasoning"."""


# =============================================================================
# STORY VALIDATION JSON SCHEMA (for OpenRouter Structured Outputs)
# =============================================================================

STORY_VALIDATION_JSON_SCHEMA = {
    "name": "story_validation",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pass", "fail"],
                "description": "Whether the story passes validation. 'pass' if appropriate, 'fail' if not."
            },
            "reasoning": {
                "type": "string",
                "description": "If status is 'fail', a short parent-friendly explanation. If 'pass', empty string."
            }
        },
        "required": ["status", "reasoning"],
        "additionalProperties": False
    }
}


def get_story_validation_response_format() -> dict:
    """
    Get the response_format parameter for structured validation outputs.

    Returns:
        Dict with type and json_schema for OpenRouter API
    """
    return {
        "type": "json_schema",
        "json_schema": STORY_VALIDATION_JSON_SCHEMA
    }


def build_story_validation_prompt(
    title: str,
    story_text: str,
    age_min: int,
    age_max: int,
) -> str:
    """
    Build the prompt for story validation.

    Args:
        title: Story title
        story_text: Full story text
        age_min: Minimum target age
        age_max: Maximum target age

    Returns:
        Formatted prompt string
    """
    return STORY_VALIDATION_PROMPT_TEMPLATE.format(
        title=title,
        story_text=story_text,
        age_min=age_min,
        age_max=age_max,
    )


def parse_story_validation_response(response_text: str) -> dict:
    """
    Parse the LLM validation response.

    Args:
        response_text: Raw text response from LLM (should be valid JSON with structured outputs)

    Returns:
        Dict with "status" ("pass"/"fail") and "reasoning" (string)
    """
    empty = {"status": "fail", "reasoning": "Unable to validate story content."}

    try:
        text = response_text.strip()

        # Try direct JSON parse first (structured outputs)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: extract JSON from potential markdown wrapping
            json_match = re.search(r'\{[\s\S]*\}', text)
            if not json_match:
                logger.error("Could not find JSON in validation response")
                return empty
            data = json.loads(json_match.group())

        # Validate structure
        if not isinstance(data, dict):
            logger.error("Validation response is not a JSON object")
            return empty

        status = data.get("status", "fail")
        reasoning = data.get("reasoning", "")

        if status not in ("pass", "fail"):
            logger.error(f"Invalid validation status: {status}")
            return empty

        return {
            "status": str(status),
            "reasoning": str(reasoning),
        }

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Failed to parse validation response: {e}")
        return empty


# =============================================================================
# PROMPT BUILDING
# =============================================================================

# Map length to target page count
LENGTH_TO_PAGES = {
    "short": (6, 8),
    "medium": (10, 12),
    "long": (14, 16),
}


# =============================================================================
# STORY RE-SPLIT PROMPT TEMPLATE
# =============================================================================

STORY_RESPLIT_PROMPT_TEMPLATE = """You are a children's book page layout expert. Your job is to split a story into pages for a children's book aimed at ages {age_min}-{age_max}.

CRITICAL RULES:
- You are SPLITTING text into pages, NOT writing or rewriting the story
- Every word of the original story text MUST appear in the output pages, in the original order
- Do NOT add, remove, or change any words
- Do NOT fix grammar, spelling, or punctuation
- Do NOT rephrase or paraphrase anything
- The concatenation of all page texts must exactly equal the original story text

PAGE SPLITTING GUIDELINES:
- Each page should have 1-2 simple sentences (suitable for ages {age_min}-{age_max})
- Break at natural narrative pauses:
  * Scene changes or new settings
  * New character actions or events
  * Emotional shifts or reactions
  * Dialogue boundaries
  * Before/after a climactic moment
- Aim for roughly even page lengths (no single-word pages, no overly long pages)
- A typical children's book for this age has 6-16 pages of content

---

STORY TITLE: {title}

STORY TEXT:
{story_text}

---

YOUR TASK:
Split the story text above into pages. Return the result as structured JSON with "title" (echo back the title) and "pages" (array of objects with "text" field). Every word must be preserved exactly."""


# =============================================================================
# STORY RE-SPLIT JSON SCHEMA (for OpenRouter Structured Outputs)
# =============================================================================

STORY_RESPLIT_JSON_SCHEMA = {
    "name": "story_resplit",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The story title (echoed back from input)"
            },
            "pages": {
                "type": "array",
                "description": "Ordered list of story pages with the original text split into page-sized chunks",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text content for this page. 1-2 simple sentences from the original story."
                        }
                    },
                    "required": ["text"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["title", "pages"],
        "additionalProperties": False
    }
}


def get_story_resplit_response_format() -> dict:
    """
    Get the response_format parameter for structured re-split outputs.

    Returns:
        Dict with type and json_schema for OpenRouter API
    """
    return {
        "type": "json_schema",
        "json_schema": STORY_RESPLIT_JSON_SCHEMA
    }


def build_story_resplit_prompt(
    title: str,
    story_text: str,
    age_min: int,
    age_max: int,
) -> str:
    """
    Build the prompt for story re-splitting.

    Args:
        title: Story title
        story_text: Full story text to split into pages
        age_min: Minimum target age
        age_max: Maximum target age

    Returns:
        Formatted prompt string
    """
    return STORY_RESPLIT_PROMPT_TEMPLATE.format(
        title=title,
        story_text=story_text,
        age_min=age_min,
        age_max=age_max,
    )


def parse_story_resplit_response(response_text: str) -> dict:
    """
    Parse the LLM re-split response.

    Args:
        response_text: Raw text response from LLM (should be valid JSON with structured outputs)

    Returns:
        Dict with "title" (str) and "pages" (list of {"text": str}),
        or empty structure on failure.
    """
    empty = {"title": "", "pages": []}

    try:
        text = response_text.strip()

        # Try direct JSON parse first (structured outputs)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: extract JSON from potential markdown wrapping
            json_match = re.search(r'\{[\s\S]*\}', text)
            if not json_match:
                logger.error("Could not find JSON in re-split response")
                return empty
            data = json.loads(json_match.group())

        # Validate structure
        if not isinstance(data, dict):
            logger.error("Re-split response is not a JSON object")
            return empty

        title = data.get("title", "")
        pages = data.get("pages", [])

        if not isinstance(pages, list):
            logger.error("Re-split response 'pages' is not an array")
            return empty

        # Normalize pages
        normalized_pages = []
        for page in pages:
            if isinstance(page, dict) and "text" in page:
                page_text = str(page["text"]).strip()
                if page_text:  # Skip empty pages
                    normalized_pages.append({"text": page_text})

        if not normalized_pages:
            logger.error("Re-split response has no non-empty pages")
            return empty

        return {
            "title": str(title),
            "pages": normalized_pages,
        }

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Failed to parse re-split response: {e}")
        return empty


# =============================================================================
# PROMPT BUILDING
# =============================================================================

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
