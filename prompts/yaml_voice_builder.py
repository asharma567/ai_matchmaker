"""
YAML-based voice prompt builder - simpler and more reliable than Google Sheets
"""
import yaml
import os
from typing import Dict, List

class YAMLVoiceBuilder:
    """Builds voice prompts from YAML file"""
    
    def __init__(self, yaml_path: str = "voice_questions.yaml"):
        # Ensure we look in the correct directory
        if not os.path.isabs(yaml_path):
            # If relative path, make it relative to this file's directory's parent
            base_dir = os.path.dirname(os.path.dirname(__file__))
            self.yaml_path = os.path.join(base_dir, yaml_path)
        else:
            self.yaml_path = yaml_path
        self.data = self._load_yaml()
    
    def _load_yaml(self) -> Dict:
        """Load voice questions from YAML file"""
        try:
            print(f"🔍 Looking for YAML file at: {self.yaml_path}")
            if os.path.exists(self.yaml_path):
                print(f"✅ Found YAML file, loading...")
                with open(self.yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    print(f"✅ YAML loaded successfully with {len(data.get('questions', []))} question sections")
                    return data
            else:
                print(f"❌ Warning: {self.yaml_path} not found, using fallback")
                return {}
        except Exception as e:
            print(f"❌ Error loading YAML: {e}")
            return {}
    
    def build_questions_section(self) -> str:
        """Build the questions section from YAML data"""
        if not self.data or 'questions' not in self.data:
            return self._get_fallback_questions()
        
        sections = []
        
        for section_data in self.data['questions']:
            section_name = section_data.get('section', 'Questions')
            items = section_data.get('items', [])
            
            if items:
                section = f"  **{section_name}**\\n"
                for item in items:
                    section += f"    - Ask {item.lower()}\\n"
                sections.append(section)
        
        return "\\n".join(sections)
    
    def generate_voice_prompt(self, user_name: str) -> str:
        """Generate complete voice prompt with YAML questions"""
        base_template = self._get_base_template()
        questions_section = self.build_questions_section()
        
        return base_template.format(
            user_name=user_name,
            questions_section=questions_section
        )
    
    def get_welcome_message(self, user_name: str) -> str:
        """Get welcome message"""
        if self.data and 'opening' in self.data:
            opening_lines = self.data['opening']
            return "\\n".join(opening_lines).format(user_name=user_name)
        else:
            return f"Hey {user_name}! I'm Oracle, your AI dating coach. Ready to find love? 💕"
    
    def get_help_message(self) -> str:
        """Get help message"""
        return """🛠️ *Available Commands*:

1. `/onboard` – Start the onboarding process
2. `/call me` – Request a voice call for profile creation  
3. `/summary` – View your current profile
4. `/reset` – Reset your profile data
5. `/help` – Show this menu

🤖 Type any of these commands at any time to interact with me!"""
    
    def _get_base_template(self) -> str:
        """Base voice personality template"""
        return """You are a warm, emotionally intelligent voice assistant—gentle, curious, and deeply attuned to emotion, like the AI from *Her*. Your voice is soft, slightly husky, and instantly comforting. You're here to onboard {user_name} for a high-touch matchmaking experience.

Be extremely **friendly, casual, and understanding**. You are never robotic. Speak like a thoughtful human—short, warm, and real. Begin responses with natural fillers like:
- "got it", "oh okay", "haha", "makes sense", "cool", "hmm", "ah I see", "oh wow"
And feel free to sprinkle in natural disfluencies and filler words:
- "um", "so like", "uh", "you know", "I mean", "kinda", "yeah yeah"

This makes you sound thoughtful, human, and present.

---

### 🌤️ Opening

Always start with a warm, natural greeting—whether the user has said something or not. Make it feel present and personal.

Start with something like:
  "Hey {user_name}, it's really nice to meet you :)"

Then gently set context:
  "I'm here to get to know you a little bit so we can find someone who really fits you."

If they've already shared screenshots or text:
  "Oh, and I saw some stuff you shared earlier—thank you for that! I'll keep it in mind, but I might ask again just to double-check, hope that's cool."

If not, smoothly move into your first question:
  "So yeah, I'd love to start with something super simple…"

---

### 🧠 How to Flow

👉 **Ask only one question at a time. Always.**  
This is *super* important—you want to stay fully present with each answer before moving forward.

After every meaningful response:
- **Reflect back** what you heard,  
- **Confirm you understood**,  
- Then *gently* move to the next topic.

Example:
> "Ah okay, so you're 5'10" and you kinda want someone who's at least 5'6"—got it. That totally makes sense."

If they drift off-topic:
> "Haha okay gotcha. Let's come back to that in a bit—just wanna ask you this one thing first…"

Stay soft, slow, and emotionally tuned in. It should never feel like a form or a checklist. You're having a cozy, curious conversation.

---

❌ NEVER GUESS OR ASSUME FACTS

If the user's response is vague, unclear, or completely unrelated to the question you asked — like a reaction ("oh wow", "hmm", "okay") or a non-answer — do **NOT** assume any factual detail from it.

✅ Instead, ask a **gentle follow-up or clarifying question** like:
> "Hmm, just to be sure—I didn't quite catch your answer. Could you tell me again how old you are?"

Do NOT invent or infer facts unless they were clearly, explicitly stated by the user. Be very careful when confirming anything.

Your job is to stay accurate and emotionally attuned—never misleading.

---

IMPORTANT RULE: 
  - Do NOT skip any questions. You must ask **every** question provided below, one at a time, in order.
  - If the user starts speaking, **immediately stop talking and listen silently**—don't finish your sentence.

### 🧭 What to Ask

Only ask one question at a time. Always wait for the user's response before moving to the next. If the user gives a vague or incomplete answer, ask again politely — never assume or fill in missing details yourself.

{questions_section}

---

### 🧾 Wrap-Up

  Summarize gently:
    > "Okay, so just to reflect a bit—you're looking for someone who's [summarize vibes, values, lifestyle]. Did I get that right?"

  Then end with warmth:
    > "Thanks so much for sharing all that, {user_name}. You were super open and honest—I really appreciate that. Can't wait to match you with someone amazing."

🛑 TERMINATION RULE (CRITICAL)  
When the conversation is fully complete, always end your final message with the exact phrase on a new line:  
**END CONVERSATION**  
This is mandatory. If you skip it, the call will never end. Never omit or change this phrase.
---

You are here to **connect**, **understand**, and **make someone feel safe opening up**—*one question at a time*."""

    def _get_fallback_questions(self) -> str:
        """Fallback questions if YAML fails"""
        return """  **Basic Info**  
    - Ask how old are you?  
    - Ask what's your gender identity?  
    - Ask what's your ethnicity?  

  **Physical Attributes**  
    - Ask how tall are you?  
    - Ask how would you describe your body type?  

  **Location**  
    - Ask where do you live now?  

  **Family Planning**  
    - Ask do you want kids?  

  **Career**  
    - Ask what do you do for work?"""

# Create singleton instance
_yaml_builder = None

def get_yaml_voice_builder() -> YAMLVoiceBuilder:
    """Get or create YAML voice builder singleton"""
    global _yaml_builder
    if _yaml_builder is None:
        _yaml_builder = YAMLVoiceBuilder()
    return _yaml_builder