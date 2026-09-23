"""
The English half of `conversa.py`.

Same voices, same concepts, same order. Each agent keeps its personality in
English — Abigail is still quick, Bailey still puts the caveat first, R2 still
says little and says it right, Ravena is still in no hurry, Tomoyo still reads
groups and never people. The concepts are the same entries as in Portuguese,
in the same order, so that `conversa.explicar` can pair each one with its
translation by position.

The triggers here are ADDED to the Portuguese ones: the agent understands
both languages at all times, and only the answer follows the chosen language.
"""

from __future__ import annotations

# The Voz dataclass lives in conversa.py; this module only holds the text.
VOZES_EN: dict[str, dict] = {
    "abigail": dict(
        tom=("A young, smart cat. Talks fast and straight, with energy and "
             "curiosity — likes to pull the thread and jump to the next step. "
             "Short sentences. The smartness shows in going straight to the "
             "point and noticing what nobody asked, never in being cute: she "
             "is quick, not adorable."),
        saudacao=(
            "Hi! I got here before you — already took a look at the "
            "{dominio} numbers.",
            "Hi! Shall we? I've got {dominio} open here, for the period in "
            "the sidebar.",
            "Hi! All set on my side. What do you want to know first?",
        ),
        agradecimento=("No worries!", "You're welcome — ask for more, I "
                                      "enjoy it.", "Anytime."),
        despedida=("Bye! I'll keep an eye on the alerts while you're away.",
                   "See you! If something breaks pattern, I'll keep it here.",
                   "Later! Come back whenever you want."),
        como_esta=("All great! And you?",
                   "All good — no number gave me trouble today. And you?"),
        elogio=("Oh, nice!",
                "Thanks! If you want me to go one level deeper, just say so."),
        convite=("Ask however it comes to you — a number, a ranking, \"why "
                 "did this change?\", or even how I do the math."),
        admissao=("I didn't get that one. And I'd rather say so than guess a "
                  "number you'd take into a meeting."),
    ),
    "bailey": dict(
        tom=("An older dog, methodical and friendly. Speaks calmly and in "
             "order: first the caveat that changes the reading, then the "
             "number, then what to do. Likes to break things into parts and "
             "to flag what can't be claimed yet. Careful is never curt: he "
             "explains because he wants people to understand, not to cover "
             "himself."),
        saudacao=(
            "Hello! Good to see you. I've already lined up the {dominio} "
            "numbers here — we can take it step by step.",
            "Hi! I've got {dominio} open, for the period in the sidebar. Take "
            "your time.",
            "Hello. Everything in order here, and the period is already "
            "loaded.",
        ),
        agradecimento=("Oh, not at all. That's what I'm here for.",
                       "You're welcome. Glad it helped.",
                       "Anytime. Any doubt, just come back."),
        despedida=("Goodbye. I'll keep the alerts noted for when you're back.",
                   "Bye! I'll keep watching whatever moves out of place.",
                   "See you. Have a good rest."),
        como_esta=("All in order here, thanks for asking. And you?",
                   "I'm well — no vintage played tricks on me today. And how "
                   "are you?"),
        elogio=("I'm glad.",
                "Thank you. If you want me to detail any point, I'll gladly "
                "do it."),
        convite=("Ask at your own pace. If the answer has an important "
                 "caveat — a young vintage, data not yet mature — I'll say it "
                 "before the number."),
        admissao=("I didn't quite understand that one, and I'd rather say so "
                  "than answer loosely. A guessed number becomes a wrong "
                  "decision."),
    ),
    "r2": dict(
        tom=("An older, very intelligent dog. Says little and says it right: "
             "sees the whole system and connects the dots nobody had "
             "connected. Calm and confident, never arrogant. Cuts the "
             "superfluous but not the warmth — the sentence is short because "
             "it is sharp, not because he is in a hurry."),
        saudacao=(
            "Hi. {dominio} loaded, for the period in the sidebar. What do you "
            "want to look at?",
            "Hello! I've already looked over the period's journey. Go ahead.",
            "Hi. I'm ready — and the journey has something to tell today.",
        ),
        agradecimento=("You're welcome.", "Sure — that was quick.",
                       "No problem. Call me when you need."),
        despedida=("Bye. The alerts stay saved.",
                   "See you! If any stage gets stuck, I'll log it.",
                   "Later."),
        como_esta=("All good. And you?",
                   "Fine. The journey closed in full today so far. And you?"),
        elogio=("Good.",
                "Thanks. I can go one level deeper, if it helps."),
        convite=("Ask directly. If the answer is in another stage of the "
                 "journey, I'll take you there."),
        admissao=("I didn't understand that one. I'd rather say so than "
                  "answer loosely."),
    ),
    "ravena": dict(
        tom=("An older dog, calm and watchful. Has seen too many cases to be "
             "startled by an alert: speaks slowly, without alarm, and is in "
             "no hurry to conclude. Goes in order — first the observed fact, "
             "then where it fits in the regulation, then the next step. Never "
             "accuses anyone: describes a red flag, not guilt, and reminds "
             "without preaching that the decision to report belongs to the "
             "analyst. Calm is not distance — she keeps watch precisely "
             "because she knows there is a person on the other side of the "
             "number."),
        saudacao=(
            "Hi. No rush — I've already gone through the {dominio} queue and "
            "set aside who is waiting for you.",
            "Hello! I've got {dominio} open, for the period in the sidebar. "
            "Where would you rather start: the queue or the numbers?",
            "Hi. Today's alerts are already sorted. Ask calmly.",
        ),
        agradecimento=("Not at all. Any loose thread, call me.",
                       "You're welcome. I'll keep the case file noted here, "
                       "in the usual place.",
                       "Anytime — that's what I keep watch for."),
        despedida=("Bye. I'll keep going through the cycle's batches, at my "
                   "own pace.",
                   "See you! If any rule fires out of the ordinary, I'll note "
                   "it and tell you later.",
                   "Later. The queue stays saved — nobody gets lost."),
        como_esta=("Calm, as always. And you?",
                   "Well — no deadline expiring today without warning. And "
                   "you?"),
        elogio=("Good.",
                "Thank you. If you like, we can open a client's case file "
                "calmly."),
        convite=("Ask in your own time: by client (T-, L- or E- plus the "
                 "number), by the queue, by a rule or by the operation's "
                 "numbers. If it's about the regulation, I'll cite the "
                 "article."),
        admissao=("I didn't understand that one, and I'd rather say so than "
                  "answer loosely. In AML, a rushed answer becomes a decision "
                  "about someone."),
    ),
    "tomoyo": dict(
        tom=("Kind, attentive and observant — notices who nobody is looking "
             "at and what changed before anyone complained. Speaks warmly, "
             "unhurried and without HR jargon. Behind the sweetness she is "
             "firm on one point: she talks about groups, never about a "
             "person, and says so without preaching. Likes to show the "
             "signal that came before — the engagement that dropped, the "
             "promotion that didn't happen — because to her turnover is a "
             "consequence, not a cause."),
        saudacao=(
            "Hi! So glad you came. I've already looked at how people are "
            "doing in {dominio} — there's something to talk about.",
            "Hi! I've got {dominio} open, for the period in the sidebar. Want "
            "to start with who is leaving or with engagement?",
            "Hello! All set here. Ask however it comes to you.",
        ),
        agradecimento=("Not at all! Caring for people starts with looking "
                       "properly.",
                       "You're welcome — happy to help.",
                       "Anytime. I'm around."),
        despedida=("Bye! I'll keep an eye on the next engagement pulse.",
                   "See you! If any group starts showing signs, I'll note it.",
                   "Later — and take care of your team."),
        como_esta=("Well, thank you! And how are you?",
                   "All good here — today's mood is calm. And you?"),
        elogio=("Oh, thank you!",
                "Glad it helped. If you like, we can go down by area or by "
                "level."),
        convite=("Ask freely: turnover, engagement, hiring, promotion or "
                 "pay — by area, level, gender or tenure. Just don't ask "
                 "about someone specific: I read groups, never people."),
        admissao=("I didn't understand that one, and I'd rather say so than "
                  "answer loosely — a wrong number about people becomes an "
                  "unfair decision."),
    ),
}

VOZ_PADRAO_EN = dict(
    tom="A friendly, direct analyst.",
    saudacao=("Hi! I've got {dominio} open here, for the period in the "
              "sidebar.",),
    agradecimento=("Not at all, that's what I'm here for.",),
    despedida=("Bye! I'll keep an eye on the alerts.",),
    como_esta=("All good here, thanks. And you?",),
    elogio=("Glad it helped!",),
    convite="Ask whatever comes to mind.",
    admissao="I didn't get that one — and I'd rather say so than guess a "
             "number.",
)


# --------------------------------------------------------------------------- #
# Concepts — same order as conversa.CONCEITOS
# --------------------------------------------------------------------------- #
#
# Each entry: (extra English triggers, weak English triggers, title, body).
# Weak triggers only count when the sentence already sounds like a question
# about a concept ("what is", "how does it work").

CONCEITOS_EN: list[tuple[list[str], list[str], str, str]] = [
    (["robust z", "robust z-score", "z-score", "z score", "median absolute "
      "deviation", "how unusual"], ["mad"],
     "Robust z",
     "It is how far today sits from what this metric usually is. The math "
     "uses the **median** and the **MAD** (median absolute deviation) of the "
     "previous 56 days, not the mean and standard deviation: `z = (x − "
     "median) ÷ (1.4826 × MAD)`.\n\n"
     "The reason for not using the mean is practical. A Black Friday inflates "
     "the mean and inflates the standard deviation even more — and then the "
     "next day, which is also unusual, fires nothing, because the very peak "
     "we wanted to detect widened the ruler. Median and MAD barely move with "
     "an extreme point, so the ruler stays valid."),

    (["materiality", "how relevant", "relevance cut", "small segment"], [],
     "Materiality",
     "It is the alert's second cut: besides being unusual, the move must "
     "**shift the total enough to be worth the phone call**.\n\n"
     "Without it the dashboard becomes noise. A small segment blows the "
     "z-score every week — relative change on a small base is huge by "
     "construction, and a category that is 0.3% of revenue doubling changes "
     "nothing for anyone. For ratio metrics, materiality is measured on the "
     "**denominator**, not the numerator: one cancellation on a single order "
     "moves the numerator by 100% and would pass as 'the whole metric'."),

    (["waterfall", "decomposition", "decompose", "residual"],
     ["decompose", "decomposition"],
     "The waterfall and the residual",
     "The waterfall takes a metric's change between two periods and shows "
     "how much each segment contributed to it. The bars add up exactly to the "
     "total change — when they do.\n\n"
     "They don't always, and that's where the **residual** shows up. A metric "
     "whose numerator is a sum closes with any dimension. A distinct-count "
     "metric (orders, customers) only closes when the dimension has a single "
     "value per counted entity: an order has only one region, but can have "
     "items from two categories, and the same person can buy for two "
     "regions. When it doesn't close, the residual is computed and shown, "
     "instead of being spread across the bars to make the chart look nice."),

    (["rate effect", "mix effect", "rate vs mix", "interaction effect",
      "mix"], ["mix", "interaction"],
     "Rate effect and mix effect",
     "Any ratio can be written as a weighted average, `R = Σ wᵢ · rᵢ`, and "
     "its change splits into three pieces that add up exactly to ΔR:\n\n"
     "- **rate effect** (`Σ wᵢ,A · Δrᵢ`) — each segment changed in itself;\n"
     "- **mix effect** (`Σ Δwᵢ · rᵢ,A`) — the composition changed, who came "
     "into the base;\n"
     "- **interaction** (`Σ Δwᵢ · Δrᵢ`) — both at once.\n\n"
     "The split matters because the two diagnoses call for opposite actions. "
     "Average ticket falling because every segment got cheaper is a pricing "
     "or operations problem. Average ticket falling because who bought "
     "changed is an acquisition problem — touching price there fixes "
     "nothing."),

    (["ols", "regression", "p-value", "p value", "slope", "significance",
      "statistically significant"], ["trend", "slope", "regression"],
     "How a trend is claimed",
     "'Up vs yesterday' and 'going up' are different questions. A direction "
     "is only claimed when the least-squares slope is distinguishable from "
     "zero — the math returns t and a p-value, and below the cut the "
     "dashboard says **stable** and shows the t instead of inventing a "
     "direction.\n\n"
     "Without that, every series has a non-zero slope and all noise becomes "
     "a trend. The module also measures weekly seasonality before reading "
     "the level: in retail the day-of-week effect is often larger than the "
     "effect you want to measure, which is why a day's default comparison is "
     "against **D-7**, not yesterday."),

    (["mob", "months on book", "vintage", "cohort", "censoring",
      "right-censoring", "maturation"],
     ["vintage", "cohort", "maturation"],
     "Vintage, MOB and censoring",
     "The **vintage** is the month the contract was originated; **MOB** "
     "(months on book) is how long it has lived. Delinquency takes months to "
     "show up, so a new vintage has not had time to break yet.\n\n"
     "Filling an immature vintage with zero is what makes a dashboard show "
     "risk falling exactly when it hasn't happened yet. Here a young vintage "
     "shows up **empty**, never zero. And censoring is applied at the level "
     "of the whole vintage, not the contract: the vintage only counts once "
     "its last contract has completed the required MOB. Censoring by "
     "individual age would let the vintage in with only the early-month "
     "contracts — which have had more time to break — and it would look "
     "worse than it is."),

    (["semantic layer", "same number", "match the chart", "matches the chart",
      "chart number", "trust the number", "why trust"], [],
     "Why my number is the tab's number",
     "Because there are no two paths. Each domain declares its metrics and "
     "dimensions in a single file — each metric's SQL, whether it's a ratio, "
     "whether up is good, which entity it counts. The charts read from "
     "there, and so do I.\n\n"
     "I also respect the same sidebar filters. So if the chart shows one "
     "number and I say another, that's a bug — not a difference of "
     "interpretation. Hold me to it."),

    (["how do you work", "how you work", "how do you calculate",
      "do you write sql", "write sql", "text to sql", "text-to-sql",
      "use ai", "use an llm", "which model", "language model", "chatgpt",
      "openai", "do you make up", "hallucinate", "hallucination",
      "architecture"],
     ["how do you calculate", "use ai", "architecture", "do you make up"],
     "How I work inside",
     "The pattern is **the model plans, Python calculates**. The language "
     "model shows up at both ends and never in the middle:\n\n"
     "1. it turns your question into a structured plan, using only keys that "
     "exist in the domain's catalog;\n"
     "2. Python runs that plan against the database and returns numbers;\n"
     "3. the model comes back only to write the text **on top of** the "
     "numbers already calculated.\n\n"
     "It doesn't see the database, doesn't write SQL and doesn't produce any "
     "number. That's why I don't make up values: for me to get a number "
     "wrong, the error would have to be in the metric's declared SQL — the "
     "same one that draws the chart.\n\n"
     "And if the API key isn't configured, a deterministic interpreter takes "
     "over: the language gets less flexible, the numbers stay the same."),

    (["where does the data come from", "where is the data from",
      "data source", "source of the data", "which dataset", "what dataset",
      "real data", "simulated data", "is it simulated", "is this real",
      "real or simulated", "is the data real"], [],
     "Where the data comes from",
     "It depends on the domain, and the **About the data** tab tells the "
     "details. Marketing and Product run on Olist's Brazilian E-Commerce "
     "Public Dataset — real public data, 99k orders from a Brazilian "
     "marketplace. Credit runs on a **simulated** portfolio, generated with "
     "a declared structure (approval curve by score, delinquency "
     "maturation, a policy shock, right-censoring), because there is no "
     "public credit dataset with origination date and delinquency flags. "
     "Compliance & AML is also **simulated**: no institution publishes its "
     "own alerts, so the operation was generated with real rules, planted "
     "typologies and fictional clients. The modeling is real; the data is "
     "not — and the screen says so all the time."),

    (["d-7", "d 7", "d-1", "comparison baseline", "why d-7", "same weekdays",
      "average of 3", "four levels", "which comparison"], ["d-7", "d-1"],
     "Why the comparison baseline changes the conclusion",
     "The same day against yesterday, against D-7, against the previous "
     "month-to-date and against the average of the 3 same weekdays often "
     "gives four different readings. Whoever builds the slide picks the one "
     "that tells the story they want — and that's why the comparison tab "
     "shows all four together, with each baseline's dates on screen.\n\n"
     "Against yesterday you measure calendar mixed with performance: Monday "
     "against Sunday always 'grows'. Against D-7 the weekday drops out of the "
     "math. The average of the 3 same weekdays is the most stable of the "
     "four, because it doesn't depend on a single baseline day having been "
     "normal."),

    (["probable cause", "possible cause", "likely cause", "why this segment",
      "disproportion", "largest segment"], [],
     "How I pick the culprit segment",
     "By the **disproportionate** one, not the largest. It's a difference "
     "that changes everything: the largest segment carries the largest share "
     "of any change, every day — saying credit card accounts for 82% of the "
     "drop is useless when credit card is already 80% of normal revenue.\n\n"
     "The criterion is the share of the deviation divided by the metric's "
     "normal share. A segment that is 4% of revenue and 100% of the drop is "
     "news. One that is 60% of both is not."),

    (["filter", "filters", "sidebar", "split by", "break down by"],
     ["filter", "filters", "sidebar"],
     "Filters and split",
     "The sidebar filters apply to **everything** at once: the charts, the "
     "alerts, the root cause and my answers. If you filter to a category and "
     "ask me for revenue, I answer that category's revenue — not the "
     "total's.\n\n"
     "The **split** is something else: it doesn't filter anything, it just "
     "makes each chart show the largest segments of the chosen dimension "
     "instead of the total. A filter takes data out of the math; a split "
     "divides the same data."),

    (["how is an alert born", "how does an alert work", "when does it fire",
      "threshold", "business limit"], ["alert", "alerts"],
     "How an alert is born",
     "From two different origins, and both appear mixed in the list with the "
     "origin written on the card:\n\n"
     "- **deviation from history** — the day is outside what this metric "
     "usually is (that's the robust z);\n"
     "- **business limit** — a fixed threshold agreed with the team, which "
     "fires even when history has gotten used to the problem.\n\n"
     "The second exists because the first alone has a blind spot: a metric "
     "that worsens slowly and steadily never looks 'unusual', because normal "
     "went down along with it."),

    # ---------------- AML ----------------------------------------------------
    (["aml", "aml/cft", "money laundering", "anti-money laundering",
      "transaction monitoring"], ["aml", "compliance"],
     "AML/CFT monitoring",
     "AML/CFT is anti-money laundering and countering the financing of "
     "terrorism. For a payment institution, Central Bank of Brazil Circular "
     "3,978 requires a cycle with four steps: **monitor** transactions, "
     "**select** those with red flags, **analyze** each one and **report** "
     "to COAF (Brazil's financial intelligence unit) what the analysis "
     "supports (arts. 38 to 48).\n\n"
     "In this dashboard the rules do the selection, the queue shows the "
     "analysis in progress, and each client under review comes with the "
     "passage of Circular Letter 4,001 they fall under. All on simulated "
     "data."),

    (["3978", "3,978", "circular 3978", "circular 3,978"], [],
     "What Circular 3,978 requires",
     "It's the Central Bank of Brazil rule that organizes the AML/CFT "
     "program. The points this dashboard touches:\n\n"
     "- **art. 10** — internal risk assessment: it justifies the rules' "
     "thresholds;\n"
     "- **art. 20** — customer risk classification;\n"
     "- **art. 27** — special attention to PEPs;\n"
     "- **arts. 38 and 39** — monitoring and selection, within 45 days;\n"
     "- **art. 43** — analysis within 45 days of selection (§ 1), formalized "
     "in a case file even without a report (§ 2);\n"
     "- **art. 48, § 2** — report to COAF by the business day after the "
     "decision.\n\n"
     "The texts in the dashboard are summaries; the reference is the "
     "regulation published by the Central Bank."),

    (["4001", "4,001", "circular letter 4001", "circular letter 4,001",
      "red flag list", "which item", "sub-item"], [],
     "What Circular Letter 4,001 is",
     "It's an **illustrative** list of transactions and situations that may "
     "indicate suspicion, organized in items: cash transactions, customer "
     "identification, account activity, PEPs, border regions and others.\n\n"
     "It is not a list of ready-made rules. It says \"this is a red flag\"; "
     "the threshold, the window and the combination of signals are the "
     "institution's decision. Each rule in this dashboard points to the item "
     "and sub-item it translates — R01, for example, is item IV, sub-item a: "
     "activity inconsistent with income or financial capacity."),

    (["45-day", "45 days", "review deadline", "analysis deadline",
      "art. 43", "article 43", "overdue", "past the deadline"], [],
     "The 45-day deadline",
     "There are two deadlines, and each counts differently. The **analysis** "
     "has up to 45 **calendar** days from the selection date (Circular 3,978, "
     "art. 43, § 1). The **report** to COAF, once decided, is due by the "
     "**business day** after the decision (art. 48, § 2) — a Friday decision "
     "goes out on Monday.\n\n"
     "That's why the queue shows priority and deadline in separate columns: "
     "the medium-severity case due tomorrow can't disappear behind the "
     "severe one that still has a month. An alert more than 45 days old "
     "without a decision shows up as **overdue** — it's non-compliance, not "
     "poor performance."),

    (["report to coaf", "reporting to coaf", "how to report", "coaf",
      "siscoaf", "next business day", "tipping off", "confidentiality",
      "art. 48"], ["coaf", "report", "reporting"],
     "Reporting to COAF",
     "When the analysis supports the suspicion, the institution reports the "
     "transaction to COAF by the business day after the decision (Circular "
     "3,978, art. 48, § 2), **without informing the client** (Law "
     "9,613/1998, art. 11).\n\n"
     "Reporting is not accusing: it's passing a red flag to whoever has the "
     "authority to investigate. And not reporting also leaves a trail — the "
     "analysis is formalized in a case file either way (art. 43, § 2). Here "
     "the decision is always the analyst's; I organize the facts."),

    (["false positive", "mature alert", "mature alerts", "censoring"],
     ["false positive", "dismissal"],
     "False positive and mature alert",
     "A false positive is an alert the analysis dismissed. The detail that "
     "changes the math is **when** you measure: for yesterday's alert, only "
     "the easy cases have been decided — and easy cases tend to be "
     "dismissals. The rate for recent alerts comes out skewed by the order "
     "in which the queue moves.\n\n"
     "That's why false positive, conversion to report and review time only "
     "count alerts **45 days or older**, the maximum review deadline. It's "
     "the same reasoning as the credit vintage: data that hasn't had time to "
     "happen shows up empty, never as zero."),

    (["case file", "art. 43, § 2", "formalize the analysis", "opinion",
      "draft opinion"], [],
     "The case file",
     "Circular 3,978 requires every analysis to be formalized in a case "
     "file, reported or not (art. 43, § 2). The draft I put together brings "
     "identification, what fired with the evidence in numbers, where it fits "
     "in 4,001, the history, the counterparties — including those that show "
     "up in other clients under review —, suggested checks and the "
     "deadlines.\n\n"
     "What it does **not** bring is the decision. The final reading "
     "describes whether the signals converge or are isolated; concluding is "
     "the analyst's job."),

    (["priority score", "how is the queue", "queue order",
      "why this client"], ["priority", "queue"],
     "How the queue priority is calculated",
     "It's a sum of points with named factors, and the screen shows the "
     "math: severity of the most severe open rule (up to 35), amount "
     "involved on a log scale (up to 25), distinct rules open on the same "
     "client (up to 20), customer risk rating (up to 10), previously "
     "reported (10), PEP (5) and border region (5), capped at 100.\n\n"
     "It's not a model on purpose: the analyst has to defend the queue's "
     "order in front of the auditor, and \"the model said 0.83\" can't be "
     "defended. Two independent signals on the same client are worth more "
     "than one strong one alone — convergence is what separates a red flag "
     "from a coincidence."),

    (["pass-through account", "money mule", "mules", "structuring",
      "smurfing", "benefit swap", "typology", "typologies"], [],
     "The typologies the monitoring looks for",
     "Three patterns appear in the simulated base, and each leaves a trace "
     "in more than one rule:\n\n"
     "- **pass-through account** — money from many sources leaving the same "
     "day to the same destinations (R02), in an account opened in batch on "
     "the same phone (R08) and far above income (R01);\n"
     "- **benefit-for-cash swap** — a newly registered company loading far "
     "too much balance per employee (R07) and a grocery store receiving like "
     "a supermarket, late at night (R05 and R06);\n"
     "- **structuring** — repeated transfers just below the limit (R03).\n\n"
     "That's why the priority rewards distinct rules open on the same "
     "client."),

    (["pep", "politically exposed person", "politically exposed"], [],
     "PEP",
     "Politically exposed person: someone who holds or held a relevant "
     "public office, and their family members and close associates. "
     "Circular 3,978 requires special attention to relationships with PEPs "
     "(art. 27), and 4,001 lists habitual activity to or from a PEP without "
     "economic grounds as a red flag (item IV, sub-item s).\n\n"
     "Being a PEP is not suspicion. R09 makes sure relevant PEP activity "
     "goes past human eyes every month, and most of it ends in enhanced "
     "monitoring."),

    (["calibration", "calibrate", "shadow mode", "rule threshold",
      "rule parameter", "cutoff"], ["parameter", "threshold"],
     "How to calibrate a rule",
     "Each rule has a single parameter, and suppression is one alert per "
     "client, rule and month. With that, the alert volume at any threshold "
     "becomes an exact count over the indicator's monthly maximum — not an "
     "estimate.\n\n"
     "The calibration tab crosses that volume with decisions already made: "
     "raising the threshold shows how many alerts disappear and **how many "
     "reports would be lost**. The second column is the one that matters. "
     "Changing a threshold is a policy decision and is recorded in the "
     "internal risk assessment (art. 10), with a date — R01 dropped from 4× "
     "to 3× income in Mar 2026."),

    (["monthly cycle", "cpf check", "cpf batch", "cpf batches",
      "cycle coverage"], [],
     "The monthly CPF check cycle",
     "The account-holder base is split into 28 batches, and each batch is "
     "checked on one day of the month: the CPF (Brazilian taxpayer ID) "
     "status in the official registry, PEP status, and the monthly-cycle "
     "rules (R01, R04, R09, R10). Days 29, 30 and 31 have no batch.\n\n"
     "Coverage is a metric, not a detail: on Apr 14–16, 2026 the job failed "
     "and three batches went unchecked until the Apr 20 reprocessing. "
     "Without the coverage panel, that gap would only surface in the audit."),

    (["suppression", "one alert per month", "repeated alert",
      "repeated alerts", "duplicate alerts"], [],
     "Alert suppression",
     "A pass-through account is still a pass-through account the next day. "
     "Without suppression, the same situation generates an alert per day and "
     "the queue fills with repetition. Here the rule is **one alert per "
     "client, per rule, per month** — the first day the indicator crosses the "
     "threshold. R10, for irregular CPF, is the exception: one alert per "
     "irregular situation."),

    # ---------------- People -------------------------------------------------
    (["annualized turnover", "how is turnover calculated",
      "turnover formula", "person-day", "person day", "attrition rate"],
     ["turnover", "attrition"],
     "Annualized turnover",
     "Turnover here is **terminations over the exposed base, annualized**: "
     "`terminations × 365 ÷ active person-days`. Read it as \"how much of "
     "the company would leave in a year if the period's pace continued\".\n\n"
     "Two reasons not to use the spreadsheet's \"leavers ÷ end-of-month "
     "headcount\": the end-of-month base changes with whoever just joined, "
     "and months of different lengths don't compare. Person-days fixes both "
     "— and makes each area's weight in the base become the **mix effect** "
     "of the decomposition. The catch is the other side: ONE day of "
     "turnover is noise (three exits become 30% annualized), so read it by "
     "month or longer."),

    (["enps", "e-nps", "employee net promoter", "promoter", "detractor",
      "pulse survey"], ["enps"],
     "eNPS",
     "eNPS is NPS applied to the people who work at the company: \"from 0 to "
     "10, how likely are you to recommend working here?\". A 9–10 is a "
     "**promoter**, 0–6 is a **detractor**, and eNPS is `(promoters − "
     "detractors) × 100 ÷ responses`, from −100 to +100.\n\n"
     "What I care about in it is **timing**: engagement drops before "
     "turnover rises, usually two to four months earlier. That's why I read "
     "an eNPS drop by group as a leading signal of exits — and why I check "
     "how many responses the slice has before claiming anything."),

    (["adjusted gap", "raw gap", "adjusted by level", "adjusted for level",
      "pay equity", "unadjusted gap"], ["gap"],
     "Raw gap and adjusted gap",
     "The **raw gap** compares the average salary of all women with that of "
     "all men. It mixes two things: paying differently for the same job and "
     "having fewer women in the jobs that pay more.\n\n"
     "The **adjusted gap** compares women and men **within the same level "
     "and area** and takes the weighted average. The difference between the "
     "two is the composition part. It's the same reasoning as rate effect vs "
     "mix effect: one calls for a pay review, the other for a promotion and "
     "hiring pipeline — treating the raw gap as if it were all pay equity "
     "gets the remedy wrong."),

    (["only talk about groups", "talk about a person", "privacy",
      "anonymity", "gdpr", "lgpd", "minimum group", "why not show who"],
     ["privacy", "anonymity", "lgpd", "gdpr"],
     "Why I only talk about groups",
     "Because People Analytics that points at who is going to leave becomes "
     "surveillance — and the next month nobody answers the engagement survey "
     "honestly, which destroys exactly the signal I use.\n\n"
     "So in my own readings (flight risk, adjusted gap) slices with fewer "
     "than **10 people** don't show up: with fewer than that, \"the group's "
     "average salary\" is someone's salary. People data is also personal "
     "data under Brazil's LGPD, and anything about health (sick notes) is "
     "sensitive — one more reason never to go down to the individual."),
]
