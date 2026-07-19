import 'dart:convert';

String _cleanOption(String value) => value
    .trim()
    .replaceFirst(RegExp(r'^[-•]\s*'), '')
    .replaceAll(RegExp(r'[*_`]'), '')
    .trim();

enum SessionStage {
  intake,
  interviewing,
  readyForAdvice,
  awaitingFeedback,
  awaitingOutcome,
  completed,
}

enum TurnState { ask, advise, resolve, safety }

class AppCredentials {
  const AppCredentials({required this.apiKey, required this.folderId});
  final String apiKey;
  final String folderId;
}

class ChatMessage {
  ChatMessage({required this.role, required this.text, DateTime? createdAt})
    : createdAt = createdAt ?? DateTime.now();
  final String role;
  final String text;
  final DateTime createdAt;

  Map<String, dynamic> toJson() => {
    'role': role,
    'text': text,
    'created_at': createdAt.toUtc().toIso8601String(),
  };
}

class UserQuestion {
  const UserQuestion({
    required this.message,
    this.field,
    this.quickReplies = const [],
  });
  final String message;
  final String? field;
  final List<String> quickReplies;

  factory UserQuestion.fromJson(Map<String, dynamic>? json) => UserQuestion(
    message: (json?['message'] as String? ?? '').trim(),
    field: json?['field'] as String?,
    quickReplies: (json?['quick_replies'] as List? ?? const [])
        .whereType<String>()
        .map(_cleanOption)
        .where((value) => value.isNotEmpty)
        .take(4)
        .toList(),
  );
}

class CaseState {
  CaseState({
    required this.id,
    this.stage = SessionStage.intake,
    Map<String, dynamic>? request,
    Map<String, dynamic>? facts,
    List<Map<String, dynamic>>? hypotheses,
    List<String>? missingFields,
    List<String>? askedFields,
    List<String>? rejectedAdvice,
    List<String>? relevantHistory,
  }) : request = request ?? {},
       facts = facts ?? {},
       hypotheses = hypotheses ?? [],
       missingFields = missingFields ?? [],
       askedFields = askedFields ?? [],
       rejectedAdvice = rejectedAdvice ?? [],
       relevantHistory = relevantHistory ?? [];

  final String id;
  SessionStage stage;
  final Map<String, dynamic> request;
  final Map<String, dynamic> facts;
  final List<Map<String, dynamic>> hypotheses;
  final List<String> missingFields;
  final List<String> askedFields;
  final List<String> rejectedAdvice;
  final List<String> relevantHistory;
  AdviceResult? lastAdvice;

  void applyPatch(Map<String, dynamic> patch) {
    for (final entry in patch.entries) {
      final value = entry.value;
      if (value != null) facts[entry.key] = value;
    }
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'stage': stage.name,
    'request': request,
    'facts': facts,
    'hypotheses': hypotheses,
    'missing_fields': missingFields,
    'asked_fields': askedFields,
    'rejected_advice': rejectedAdvice,
    'relevant_history': relevantHistory,
    if (lastAdvice != null) 'last_advice': lastAdvice!.toJson(),
  };

  String encode() => jsonEncode(toJson());
}

class IntakeResult {
  const IntakeResult({
    required this.request,
    required this.knownFacts,
    required this.hypotheses,
    required this.informationPlan,
    required this.firstQuestion,
  });
  final Map<String, dynamic> request;
  final Map<String, dynamic> knownFacts;
  final List<Map<String, dynamic>> hypotheses;
  final List<Map<String, dynamic>> informationPlan;
  final UserQuestion firstQuestion;

  factory IntakeResult.fromJson(Map<String, dynamic> json) => IntakeResult(
    request: Map<String, dynamic>.from(json['request'] as Map? ?? {}),
    knownFacts: Map<String, dynamic>.from(json['known_facts'] as Map? ?? {}),
    hypotheses: (json['hypotheses'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
    informationPlan: (json['information_plan'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
    firstQuestion: UserQuestion.fromJson(
      json['first_question'] as Map<String, dynamic>?,
    ),
  );
}

class InterviewResult {
  const InterviewResult({
    required this.statePatch,
    required this.status,
    required this.nextQuestion,
    required this.hypotheses,
  });
  final Map<String, dynamic> statePatch;
  final String status;
  final UserQuestion nextQuestion;
  final List<Map<String, dynamic>> hypotheses;

  bool get readyForAdvice => status == 'ready_for_advice';

  factory InterviewResult.fromJson(Map<String, dynamic> json) =>
      InterviewResult(
        statePatch: Map<String, dynamic>.from(
          json['state_patch'] as Map? ?? {},
        ),
        status: json['status'] as String? ?? 'needs_clarification',
        nextQuestion: UserQuestion.fromJson(
          json['next_question'] as Map<String, dynamic>?,
        ),
        hypotheses: (json['hypotheses'] as List? ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList(),
      );
}

class AdviceResult {
  const AdviceResult({
    required this.decision,
    required this.message,
    required this.followUp,
    required this.episodeSummary,
    this.alternatives = const [],
  });
  final String decision;
  final String message;
  final String followUp;
  final String episodeSummary;
  final List<String> alternatives;

  factory AdviceResult.fromJson(Map<String, dynamic> json) => AdviceResult(
    decision: json['decision'] as String? ?? 'clarify',
    message: (json['message'] as String? ?? '').trim(),
    followUp: (json['follow_up'] as String? ?? '').trim(),
    episodeSummary: (json['episode_summary'] as String? ?? '').trim(),
    alternatives: (json['alternatives'] as List? ?? const [])
        .whereType<String>()
        .map(_cleanOption)
        .where((value) => value.isNotEmpty)
        .take(3)
        .toList(),
  );

  Map<String, dynamic> toJson() => {
    'decision': decision,
    'message': message,
    'follow_up': followUp,
    'episode_summary': episodeSummary,
    'alternatives': alternatives,
  };
}

class ReviewResult {
  const ReviewResult({
    required this.verdict,
    required this.advice,
    this.violations = const [],
  });
  final String verdict;
  final AdviceResult advice;
  final List<String> violations;

  factory ReviewResult.fromJson(Map<String, dynamic> json) => ReviewResult(
    verdict: json['verdict'] as String? ?? 'revise',
    advice: AdviceResult.fromJson(
      Map<String, dynamic>.from(json['approved_advice'] as Map? ?? {}),
    ),
    violations: (json['violations'] as List? ?? const [])
        .whereType<String>()
        .toList(),
  );
}

class MemoryDraft {
  const MemoryDraft({
    required this.episode,
    required this.retrievalText,
    this.memoryCandidates = const [],
    this.doNotStore = const [],
  });
  final Map<String, dynamic> episode;
  final String retrievalText;
  final List<Map<String, dynamic>> memoryCandidates;
  final List<String> doNotStore;

  factory MemoryDraft.fromJson(Map<String, dynamic> json) => MemoryDraft(
    episode: Map<String, dynamic>.from(json['episode'] as Map? ?? {}),
    retrievalText: (json['retrieval_text'] as String? ?? '').trim(),
    memoryCandidates: (json['memory_candidates'] as List? ?? const [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList(),
    doNotStore: (json['do_not_store'] as List? ?? const [])
        .whereType<String>()
        .toList(),
  );
}

class AgentReply {
  const AgentReply({
    required this.message,
    required this.state,
    this.quickReplies = const [],
  });
  final String message;
  final TurnState state;
  final List<String> quickReplies;
}
