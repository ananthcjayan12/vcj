DEFAULT_SHORT_DURATION = 40.0
MIN_SHORT_DURATION = 20.0
MAX_SHORT_DURATION = 60.0
PORTRAIT_WIDTH = 1080
PORTRAIT_HEIGHT = 1920
SHORT_FPS = 30
MAX_SOURCE_REELS = 2
MAX_CONCEPTS = 1
MIN_HOOK_DURATION = 1.0
MAX_CAPTION_CHARACTERS = 44
MAX_CAPTION_WORDS = 5
MIN_TEXT_SIZE = 34
MAX_ACTIVE_SHORTS = 3
SAFE_AREA = {"left": -470, "right": 470, "top": -790, "bottom": 720}
ARCHETYPES = (
    "misconception", "surprising_fact", "prediction_challenge", "exam_trap",
    "visual_explanation", "worked_example", "practical_tip", "quick_comparison",
)
DEPENDENT_PHRASES = ("as we saw earlier", "in the previous section", "now that we know", "continuing from")
SCORE_WEIGHTS = {"standalone_score": .25, "hook_score": .20, "payoff_score": .15,
                 "visual_reuse_score": .15, "audio_reuse_score": .10,
                 "exam_relevance_score": .10, "portrait_suitability_score": .05}
