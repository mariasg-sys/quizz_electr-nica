# Streamlit Quiz Trainer

This app loads `question_bank.json`, filters questions, runs multiple quiz modes, validates answers, explains answers, tracks stats, and saves progress locally in `progress.json`.

## Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Question Bank Format

Put your final `question_bank.json` next to `app.py`. The app accepts either a top-level list of questions or:

```json
{
  "questions": [
    {
      "id": "q1",
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
```

For multiple-correct questions, use `correct_answers`:

```json
"correct_answers": ["list", "tuple"]
```

Options can be strings, a dictionary, or objects with `key` and `text`.

## Quiz Modes

- Random quiz: picks from the active filtered pool.
- Topic quiz: works with the selected sidebar topic filters.
- Adaptive mode: prioritizes questions missed in previous attempts.
- Exam simulation: builds a shuffled exam queue from the filtered pool.

## Progress

Progress is saved locally to `progress.json`. Use the sidebar buttons to reset or download it.

## Phone Use

Streamlit apps are web apps, not direct installable mobile apps by default. You can still use it on a phone by running Streamlit on a computer/server and opening the app URL from the phone browser. Many mobile browsers also let you add the page to the home screen.
