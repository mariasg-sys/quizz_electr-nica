import json
import random
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st


APP_DIR = Path(__file__).parent
QUESTION_BANK_PATH = APP_DIR / "question_bank.json"
PROGRESS_PATH = APP_DIR / "progress.json"


st.set_page_config(
    page_title="Quiz Trainer",
    page_icon="Q",
    layout="wide",
    initial_sidebar_state="expanded",
)


def normalize_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalize_question(raw, index):
    options = raw.get("options", raw.get("choices", []))
    correct = raw.get("correct_answers", raw.get("correct", raw.get("answers", raw.get("answer"))))
    correct_answers = [str(item) for item in normalize_list(correct)]

    normalized_options = []
    if isinstance(options, dict):
        for key, value in options.items():
            normalized_options.append({"key": str(key), "text": str(value)})
    else:
        for option in normalize_list(options):
            if isinstance(option, dict):
                key = str(option.get("key", option.get("id", option.get("label", option.get("text", "")))))
                text = str(option.get("text", option.get("label", key)))
                normalized_options.append({"key": key, "text": text})
            else:
                text = str(option)
                normalized_options.append({"key": text, "text": text})

    option_keys = {item["key"] for item in normalized_options}
    option_texts = {item["text"] for item in normalized_options}
    cleaned_correct = []
    for answer in correct_answers:
        if answer in option_keys:
            cleaned_correct.append(answer)
        elif answer in option_texts:
            matching = next(item["key"] for item in normalized_options if item["text"] == answer)
            cleaned_correct.append(matching)
        else:
            cleaned_correct.append(answer)

    question_id = str(raw.get("id", raw.get("question_id", f"q-{index + 1}")))

    return {
        "id": question_id,
        "question": str(raw.get("question", raw.get("text", ""))).strip(),
        "topic": str(raw.get("topic", "General")).strip() or "General",
        "subtopic": str(raw.get("subtopic", "General")).strip() or "General",
        "difficulty": str(raw.get("difficulty", "Medium")).strip() or "Medium",
        "tags": [str(tag).strip() for tag in normalize_list(raw.get("tags")) if str(tag).strip()],
        "ambiguous": bool(raw.get("ambiguous", raw.get("is_ambiguous", False))),
        "options": normalized_options,
        "correct_answers": cleaned_correct,
        "explanation": str(raw.get("explanation", raw.get("why", "No explanation provided."))).strip(),
    }


@st.cache_data(show_spinner=False)
def load_question_bank():
    if not QUESTION_BANK_PATH.exists():
        return []

    with QUESTION_BANK_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        questions = payload.get("questions", payload.get("items", []))
    else:
        questions = payload

    return [
        normalize_question(question, index)
        for index, question in enumerate(questions)
        if isinstance(question, dict) and question.get("question", question.get("text"))
    ]


def load_progress():
    if not PROGRESS_PATH.exists():
        return {"answers": [], "failed_question_ids": [], "last_saved": None}
    try:
        with PROGRESS_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {"answers": [], "failed_question_ids": [], "last_saved": None}

    data.setdefault("answers", [])
    data.setdefault("failed_question_ids", [])
    data.setdefault("last_saved", None)
    return data


def save_progress(progress):
    progress["last_saved"] = datetime.now(timezone.utc).isoformat()
    with PROGRESS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(progress, handle, indent=2)


def reset_question_state(question):
    st.session_state.current_question = question
    st.session_state.submitted = False
    st.session_state.feedback = None
    st.session_state.answer_widget_key = f"answer-{question['id']}-{uuid.uuid4()}"


def all_values(questions, field):
    values = sorted({question[field] for question in questions if question[field]})
    return values


def all_tags(questions):
    values = set()
    for question in questions:
        values.update(question["tags"])
    return sorted(values)


def filter_questions(questions, selected_topics, selected_subtopics, selected_difficulties, selected_tags, ambiguous_mode):
    filtered = []
    for question in questions:
        if selected_topics and question["topic"] not in selected_topics:
            continue
        if selected_subtopics and question["subtopic"] not in selected_subtopics:
            continue
        if selected_difficulties and question["difficulty"] not in selected_difficulties:
            continue
        if selected_tags and not set(selected_tags).issubset(set(question["tags"])):
            continue
        if ambiguous_mode == "Exclude" and question["ambiguous"]:
            continue
        if ambiguous_mode == "Only ambiguous" and not question["ambiguous"]:
            continue
        filtered.append(question)
    return filtered


def pick_question(mode, filtered_questions, progress, exam_size):
    if not filtered_questions:
        return None

    if mode == "Adaptive mode":
        failed_ids = progress.get("failed_question_ids", [])
        failed_pool = [question for question in filtered_questions if question["id"] in failed_ids]
        if failed_pool and random.random() < 0.75:
            return random.choice(failed_pool)
        return random.choice(filtered_questions)

    if mode == "Exam simulation":
        if "exam_queue" not in st.session_state or not st.session_state.exam_queue:
            queue = filtered_questions[:]
            random.shuffle(queue)
            st.session_state.exam_queue = queue[:exam_size]
            st.session_state.exam_total = len(st.session_state.exam_queue)
        if st.session_state.exam_queue:
            return st.session_state.exam_queue.pop(0)
        return None

    return random.choice(filtered_questions)


def answer_is_correct(selected, correct_answers):
    return set(selected) == set(correct_answers)


def format_answers(question, answer_keys):
    labels = []
    for key in answer_keys:
        option = next((item for item in question["options"] if item["key"] == key), None)
        labels.append(option["text"] if option else key)
    return labels


def record_answer(progress, question, selected, is_correct):
    record = {
        "question_id": question["id"],
        "topic": question["topic"],
        "subtopic": question["subtopic"],
        "difficulty": question["difficulty"],
        "tags": question["tags"],
        "selected": selected,
        "correct_answers": question["correct_answers"],
        "is_correct": is_correct,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }
    progress["answers"].append(record)

    failed_ids = set(progress.get("failed_question_ids", []))
    if is_correct:
        failed_ids.discard(question["id"])
    else:
        failed_ids.add(question["id"])
    progress["failed_question_ids"] = sorted(failed_ids)
    save_progress(progress)


def calculate_stats(progress):
    answers = progress.get("answers", [])
    total = len(answers)
    correct = sum(1 for answer in answers if answer.get("is_correct"))
    accuracy = correct / total if total else 0

    topic_totals = Counter(answer.get("topic", "General") for answer in answers)
    topic_misses = Counter(answer.get("topic", "General") for answer in answers if not answer.get("is_correct"))
    weak_topics = sorted(
        topic_misses.items(),
        key=lambda item: (item[1] / topic_totals[item[0]], item[1]),
        reverse=True,
    )
    return total, correct, accuracy, weak_topics


def render_header(total, correct, accuracy, filtered_count):
    st.title("Quiz Trainer")
    st.caption("A local question-bank quiz app with adaptive practice, exam simulation, and saved progress.")

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Questions answered", total)
    col_b.metric("Correct", correct)
    col_c.metric("Accuracy", f"{accuracy:.0%}" if total else "0%")
    col_d.metric("Active question pool", filtered_count)
    st.progress(accuracy if total else 0, text="Overall accuracy")


def render_sidebar(questions):
    st.sidebar.title("Filters")
    selected_topics = st.sidebar.multiselect("Topic", all_values(questions, "topic"))
    selected_subtopics = st.sidebar.multiselect("Subtopic", all_values(questions, "subtopic"))
    selected_difficulties = st.sidebar.multiselect("Difficulty", all_values(questions, "difficulty"))
    selected_tags = st.sidebar.multiselect("Tags", all_tags(questions))
    ambiguous_mode = st.sidebar.radio(
        "Ambiguous questions",
        ["Include", "Exclude", "Only ambiguous"],
        horizontal=False,
    )

    st.sidebar.divider()
    mode = st.sidebar.radio(
        "Quiz mode",
        ["Random quiz", "Topic quiz", "Adaptive mode", "Exam simulation"],
    )
    exam_size = st.sidebar.number_input("Exam questions", min_value=1, max_value=100, value=20, step=1)

    if mode == "Topic quiz" and not selected_topics:
        st.sidebar.info("Choose one or more topics for Topic quiz.")

    return selected_topics, selected_subtopics, selected_difficulties, selected_tags, ambiguous_mode, mode, int(exam_size)


def render_question(question, progress):
    st.subheader(question["question"])
    meta = [
        f"Topic: {question['topic']}",
        f"Subtopic: {question['subtopic']}",
        f"Difficulty: {question['difficulty']}",
    ]
    if question["tags"]:
        meta.append("Tags: " + ", ".join(question["tags"]))
    if question["ambiguous"]:
        meta.append("Ambiguous")
    st.caption(" | ".join(meta))

    option_labels = {option["text"]: option["key"] for option in question["options"]}
    if len(question["correct_answers"]) != 1:
        selected_labels = st.multiselect(
            "Choose all correct answers. Leave blank if none are correct.",
            list(option_labels.keys()),
            key=st.session_state.answer_widget_key,
        )
    else:
        selected_label = st.radio(
            "Choose one answer",
            list(option_labels.keys()),
            index=None,
            key=st.session_state.answer_widget_key,
        )
        selected_labels = [selected_label] if selected_label else []

    selected_keys = [option_labels[label] for label in selected_labels]

    col_a, col_b = st.columns([1, 1])
    submitted = col_a.button("Validate answer", type="primary", disabled=st.session_state.submitted)
    next_clicked = col_b.button("Next question")

    if submitted:
        if not selected_keys and question["correct_answers"]:
            st.warning("Select an answer first.")
        else:
            is_correct = answer_is_correct(selected_keys, question["correct_answers"])
            record_answer(progress, question, selected_keys, is_correct)
            st.session_state.submitted = True
            st.session_state.feedback = {
                "is_correct": is_correct,
                "selected": selected_keys,
                "correct": question["correct_answers"],
            }
            st.rerun()

    if st.session_state.feedback:
        feedback = st.session_state.feedback
        if feedback["is_correct"]:
            st.success("Correct.")
        else:
            st.error("Not quite.")
        st.write("Correct answer:", ", ".join(format_answers(question, feedback["correct"])))
        st.info(question["explanation"])

    if next_clicked:
        st.session_state.current_question = None
        st.session_state.submitted = False
        st.session_state.feedback = None
        st.rerun()


def render_weak_topics(progress):
    total, _, _, weak_topics = calculate_stats(progress)
    if not total:
        st.write("Answer a few questions and weak topics will appear here.")
        return

    st.write("Weak topics are ranked by miss rate and number of misses.")
    topic_totals = Counter(answer.get("topic", "General") for answer in progress["answers"])
    for topic, misses in weak_topics[:5]:
        answered = topic_totals[topic]
        miss_rate = misses / answered if answered else 0
        st.progress(miss_rate, text=f"{topic}: {misses}/{answered} missed")


def main():
    questions = load_question_bank()
    progress = load_progress()

    st.markdown(
        """
        <style>
        .stApp { background: #0f1218; }
        [data-testid="stSidebar"] { background: #151a22; }
        .stButton button { border-radius: 6px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not questions:
        st.title("Quiz Trainer")
        st.warning("Add a question_bank.json file next to app.py to begin.")
        st.code(
            """
{
  "questions": [
    {
      "id": "example-1",
      "topic": "Python",
      "subtopic": "Data types",
      "difficulty": "Easy",
      "tags": ["basics"],
      "ambiguous": false,
      "question": "Which type stores true/false values?",
      "options": ["str", "bool", "list", "dict"],
      "answer": "bool",
      "explanation": "The bool type represents True and False values."
    }
  ]
}
            """.strip(),
            language="json",
        )
        return

    sidebar_values = render_sidebar(questions)
    selected_topics, selected_subtopics, selected_difficulties, selected_tags, ambiguous_mode, mode, exam_size = sidebar_values

    filtered_questions = filter_questions(
        questions,
        selected_topics,
        selected_subtopics,
        selected_difficulties,
        selected_tags,
        ambiguous_mode,
    )

    if mode == "Topic quiz" and selected_topics:
        filtered_questions = [question for question in filtered_questions if question["topic"] in selected_topics]

    if st.sidebar.button("Start fresh question"):
        st.session_state.current_question = None
        st.session_state.exam_queue = []

    if st.sidebar.button("Reset saved progress"):
        save_progress({"answers": [], "failed_question_ids": [], "last_saved": None})
        st.session_state.current_question = None
        st.rerun()

    st.sidebar.download_button(
        "Download progress",
        data=json.dumps(progress, indent=2),
        file_name="quiz_progress.json",
        mime="application/json",
    )

    total, correct, accuracy, _ = calculate_stats(progress)
    render_header(total, correct, accuracy, len(filtered_questions))

    tab_quiz, tab_stats, tab_bank = st.tabs(["Quiz", "Statistics", "Question bank"])

    with tab_quiz:
        if not filtered_questions:
            st.warning("No questions match the current filters.")
        else:
            if not st.session_state.get("current_question"):
                next_question = pick_question(mode, filtered_questions, progress, exam_size)
                if next_question is None:
                    st.success("Exam complete. Start a fresh question to run another exam.")
                else:
                    reset_question_state(next_question)

            if st.session_state.get("current_question"):
                if mode == "Exam simulation":
                    remaining = len(st.session_state.get("exam_queue", []))
                    exam_total = st.session_state.get("exam_total", remaining + 1)
                    completed = max(exam_total - remaining - 1, 0)
                    st.progress(completed / exam_total if exam_total else 0, text=f"Exam progress: {completed}/{exam_total}")
                render_question(st.session_state.current_question, progress)

    with tab_stats:
        render_weak_topics(progress)
        st.divider()
        st.write("Recent answers")
        recent = list(reversed(progress.get("answers", [])[-10:]))
        if recent:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.write("No answers recorded yet.")

    with tab_bank:
        grouped = defaultdict(int)
        for question in filtered_questions:
            grouped[(question["topic"], question["subtopic"], question["difficulty"])] += 1
        rows = [
            {"topic": topic, "subtopic": subtopic, "difficulty": difficulty, "questions": count}
            for (topic, subtopic, difficulty), count in sorted(grouped.items())
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
