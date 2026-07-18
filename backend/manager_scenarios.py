# manager_scenarios.py
# Generates workplace scenarios based on what student studied yesterday
# Used by: /manager page and push notifications

import json
import random
from datetime import datetime

# Manager personas - rotates to keep it fresh
MANAGERS = [
    {"name": "Rajesh Kumar",  "initials": "RK", "title": "Senior Engineer",    "style": "direct"},
    {"name": "Priya Sharma",  "initials": "PS", "title": "Project Lead",        "style": "friendly"},
    {"name": "Arun Mehta",    "initials": "AM", "title": "Tech Lead",           "style": "strict"},
    {"name": "Divya Nair",    "initials": "DN", "title": "Module Lead",         "style": "casual"},
]

# Format rotates daily
FORMATS = ["whatsapp", "email", "voice"]

def get_todays_format():
    """Rotates format based on day of week"""
    day = datetime.now().weekday()  # 0=Monday
    return FORMATS[day % len(FORMATS)]

def get_todays_manager(user_id: int):
    """Picks manager based on user_id + week number to feel consistent"""
    week = datetime.now().isocalendar()[1]
    return MANAGERS[(user_id + week) % len(MANAGERS)]

def get_day_label():
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return days[datetime.now().weekday()]

def build_scenario_prompt(topic: str, weakest_topic: str, manager: dict) -> str:
    """Builds prompt for RAG to generate a workplace scenario"""
    return f"""You are generating a workplace scenario for an HCL intern app.

Manager: {manager['name']} ({manager['title']})
Topic studied yesterday: {topic}
Student's weakest topic: {weakest_topic}

Create a realistic workplace scenario where the manager needs the intern to answer 
a technical question related to "{topic}". 

The scenario should:
1. Feel like a real HCL workplace situation
2. Naturally require knowledge of {topic}
3. Be urgent but not scary (morning standup, client coming, etc.)
4. Have ONE clear technical question with 4 MCQ options
5. Feel connected to real engineering work

Return JSON only:
{{
  "scenario_message": "What the manager says (1-2 sentences, casual/real)",
  "context": "Brief workplace context (1 sentence)",
  "question": "The technical question",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "answer": 0,
  "explanation": "Why the answer is correct (simple, 2-3 sentences)",
  "good_reaction": "Manager's response if correct (encouraging, 1-2 sentences)",
  "bad_reaction": "Manager's response if wrong (firm but kind, 1-2 sentences)"
}}"""


def get_scenario_for_topic(topic: str, weakest_topic: str, user_id: int) -> dict:
    """
    Main function called by Flask route.
    Returns a complete scenario for today.
    """
    manager = get_todays_manager(user_id)
    fmt     = get_todays_format()
    day     = get_day_label()

    # Try RAG-generated scenario first
    try:
        from rag import mentor_chat
        # Use RAG to find relevant content for this topic
        prompt = build_scenario_prompt(topic, weakest_topic, manager)
        result = mentor_chat(prompt, "HCL")
        
        # Try to parse JSON from response
        import re
        text = result.get('answer', '')
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            scenario_data = json.loads(json_match.group())
            return {
                "manager":       manager,
                "format":        fmt,
                "day_label":     day,
                "topic":         topic,
                "weakest_topic": weakest_topic,
                "scenario":      scenario_data,
                "generated":     True
            }
    except Exception as e:
        print(f"RAG scenario generation failed: {e}, using fallback")

    # Fallback static scenarios
    return get_fallback_scenario(topic, manager, fmt, day)


def get_fallback_scenario(topic: str, manager: dict, fmt: str, day: str) -> dict:
    """Static fallback scenarios when RAG fails"""
    
    fallbacks = {
        "Logic Gates": {
            "scenario_message": f"Good morning! Quick question before standup — which gate gives output 1 ONLY when both inputs are 1?",
            "context": "Server room alarm system needs the right gate",
            "question": "The alarm should trigger ONLY when BOTH sensors detect a problem. Which gate?",
            "options": ["OR gate", "AND gate", "NAND gate", "XOR gate"],
            "answer": 1,
            "explanation": "AND gate: output is 1 only when ALL inputs are 1. If either sensor is 0, no alarm. Perfect for 'both must trigger' situations.",
            "good_reaction": "Correct! AND gate it is. You just saved us from false alarms 👍",
            "bad_reaction": "Not quite. We need AND gate — output 1 only when BOTH inputs are 1. Review logic gates."
        },
        "Number Systems": {
            "scenario_message": "Morning! Config file update — what's the decimal value of binary 10110?",
            "context": "Server migration needs address conversion",
            "question": "Convert binary 10110 to decimal for the config file.",
            "options": ["20", "22", "18", "24"],
            "answer": 1,
            "explanation": "10110 = 16+4+2 = 22. Positions from right: 1,2,4,8,16. Multiply each 1 by its position value and add.",
            "good_reaction": "22! Correct. Config updated. Good binary skills 💪",
            "bad_reaction": "It's 22 — 16+4+2=22. Remember positional values: 1,2,4,8,16 from right."
        },
        "Boolean Algebra": {
            "scenario_message": "Hey! Can you simplify A + A·B? Need it for the circuit optimization report.",
            "context": "Circuit optimization to reduce gate count",
            "question": "Simplify the Boolean expression: A + A·B",
            "options": ["A·B", "A+B", "A", "B"],
            "answer": 2,
            "explanation": "A + A·B = A — absorption law. If A=1, whole expression is 1. If A=0, A·B=0 so expression is 0. Result is just A.",
            "good_reaction": "Perfect! A it is. That saves us 2 gates in the design 🎯",
            "bad_reaction": "It simplifies to just A. Use absorption law: A + A·B = A. Review Boolean laws."
        },
        "Flip Flops": {
            "scenario_message": "Quick — what happens to a JK flip flop when J=K=1? Need this for the counter design.",
            "context": "Digital counter design for production line",
            "question": "In a JK flip-flop, what happens when J=1 and K=1?",
            "options": ["Output is 1", "Output is 0", "Output toggles", "Invalid state"],
            "answer": 2,
            "explanation": "When J=K=1 in a JK flip-flop, the output TOGGLES — it flips from current state. This is what makes JK better than SR (which has forbidden state).",
            "good_reaction": "Toggles! Correct. That's exactly what we need for the counter 🔄",
            "bad_reaction": "J=K=1 causes toggling, not invalid state (that was SR flip-flop's problem). Review JK flip-flop."
        },
        "C Programming": {
            "scenario_message": "Found a bug — int x=10; int *p=&x; *p=25; What is x after this?",
            "context": "Code review before client demo",
            "question": "After: int x=10; int *p=&x; *p=25; — what is the value of x?",
            "options": ["10", "25", "Garbage", "Error"],
            "answer": 1,
            "explanation": "*p=25 goes to x's memory address and changes it directly. p points to x, so *p IS x. x becomes 25.",
            "good_reaction": "25! Correct. Good pointer knowledge — that's exactly the bug 🎯",
            "bad_reaction": "x becomes 25. *p dereferences the pointer — it changes x directly, not a copy. Review pointers."
        }
    }
    
    # Default if topic not found
    scenario_data = fallbacks.get(topic, fallbacks["Logic Gates"])
    
    return {
        "manager":       manager,
        "format":        fmt,
        "day_label":     day,
        "topic":         topic,
        "weakest_topic": topic,
        "scenario":      scenario_data,
        "generated":     False
    }