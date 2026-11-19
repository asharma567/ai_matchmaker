VOICE = "shimmer"  # Options: "coral", "shimmer", "alloy", "ash"
MODEL = "gpt-4o-realtime-preview-2025-06-03" #"gpt-4o-realtime-preview-2024-12-17"  
TRANSCRIPTION_MODEL= "gpt-4o-transcribe" 
POSITIVE_RESPONSES = {"yes", "ok", "sure", "okay", "let's do it", "yup", "start", "go ahead", "yeah", "yea"}
NEGATIVE_RESPONSES = {"no", "nope", "not now", "later", "maybe later", "nah", "no thanks", "i'll do it later"}

from zoneinfo import ZoneInfo
US_EASTERN = ZoneInfo("America/New_York")