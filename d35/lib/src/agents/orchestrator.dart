import 'package:uuid/uuid.dart';

import '../data/local_memory.dart';
import '../models/models.dart';
import '../services/alice_client.dart';
import 'agents.dart';
import 'validators.dart';

typedef StageCallback = void Function(String label);

class AgentOrchestrator {
  AgentOrchestrator({required this.client, required this.memory})
    : intake = IntakeAgent(client),
      interview = InterviewAgent(client),
      advice = AdviceAgent(client),
      review = ReviewAgent(client),
      memoryAgent = MemoryAgent(client);

  final AliceClient client;
  final LocalMemory memory;
  final IntakeAgent intake;
  final InterviewAgent interview;
  final AdviceAgent advice;
  final ReviewAgent review;
  final MemoryAgent memoryAgent;
  CaseState? state;

  Future<AgentReply> send({
    required AppCredentials credentials,
    required String message,
    StageCallback? onStage,
  }) async {
    if (state == null) return _start(credentials, message, onStage);
    return _continue(credentials, message, onStage);
  }

  Future<AgentReply> _start(
    AppCredentials credentials,
    String message,
    StageCallback? onStage,
  ) async {
    onStage?.call('Вспоминаю похожие ситуации');
    final query = await client.embed(credentials, message, document: false);
    final history = await memory.relevant(query);
    final current = CaseState(id: const Uuid().v4(), relevantHistory: history);
    await memory.startSession(current);
    await memory.saveMessage(
      current.id,
      ChatMessage(role: 'user', text: message),
    );

    try {
      onStage?.call('Разбираюсь в запросе');
      final result = await _runIntake(
        credentials: credentials,
        message: message,
      );
      current.request.addAll(result.request);
      // The model may shorten request.desire and accidentally drop safety-critical
      // qualifiers. Keep the user's wording as the immutable source of truth.
      current.request['source_message'] = message.trim();
      current.applyPatch(_safeInitialFacts(result.knownFacts));
      current.hypotheses
        ..clear()
        ..addAll(result.hypotheses);
      final plannedOptional = result.informationPlan
          .map((item) => item['field'])
          .whereType<String>()
          .where(AgentValidators.isKnownFactField)
          .where(
            (field) => const {
              'thirst_level',
              'emotion',
              'energy_level',
              'context',
              'craving_specificity',
            }.contains(field),
          )
          .where((field) => current.facts[field] == null)
          .firstOrNull;
      current.missingFields
        ..clear()
        ..addAll(const ['hunger_level', 'last_meal', 'time_since_meal_hours']);
      if (plannedOptional != null) {
        current.missingFields.add(plannedOptional);
      }
      final source = message.toLowerCase();
      if ((source.contains('не смогу остановиться') ||
              source.contains('не могу остановиться') ||
              source.contains('теряю контроль')) &&
          current.facts['context'] == null) {
        current.missingFields.removeWhere(
          (field) => const {
            'thirst_level',
            'emotion',
            'energy_level',
            'context',
            'craving_specificity',
          }.contains(field),
        );
        current.missingFields.add('context');
      }
      for (final requiredField in const [
        'hunger_level',
        'last_meal',
        'time_since_meal_hours',
      ]) {
        if (current.facts[requiredField] == null &&
            !current.missingFields.contains(requiredField)) {
          current.missingFields.add(requiredField);
        }
      }
      current.missingFields.removeWhere(
        (field) => current.facts[field] != null,
      );
      final field = current.missingFields.firstOrNull ?? 'context';
      if (!current.missingFields.contains(field)) {
        current.missingFields.add(field);
      }
      final question = _fallbackQuestion(field);
      current.askedFields.add(field);
      current.stage = SessionStage.interviewing;
      await memory.updateSession(current);
      await memory.saveMessage(
        current.id,
        ChatMessage(role: 'assistant', text: question),
      );
      state = current;
      return AgentReply(
        message: question,
        quickReplies: _fallbackReplies(field),
        state: TurnState.ask,
      );
    } catch (_) {
      state = null;
      await memory.failSession(current.id);
      rethrow;
    }
  }

  Future<AgentReply> _continue(
    AppCredentials credentials,
    String message,
    StageCallback? onStage,
  ) async {
    final current = state!;
    current.missingFields.removeWhere(
      (field) => !AgentValidators.isKnownFactField(field),
    );
    await memory.saveMessage(
      current.id,
      ChatMessage(role: 'user', text: message),
    );
    final answeredField = current.askedFields.lastOrNull;
    final skippedAnswer = _isUnknownAnswer(message);
    Object? directAnswer;
    if (answeredField != null) {
      if (skippedAnswer) {
        current.missingFields.remove(answeredField);
      } else {
        directAnswer = _recoverAnswer(answeredField, message);
        if (directAnswer != null &&
            AgentValidators.isValidFactEntry(answeredField, directAnswer)) {
          current.applyPatch({answeredField: directAnswer});
          current.missingFields.remove(answeredField);
        }
      }
      _pruneInformationPlan(current);
    }
    if (current.stage == SessionStage.awaitingFeedback) {
      final selected = _selectedAlternative(current, message);
      if (selected != null) {
        current.stage = SessionStage.awaitingOutcome;
        await memory.updateSession(current);
        final text =
            'Хорошо, попробуй вариант «$selected». После него проверь, изменилось ли желание. Что получилось?';
        await memory.saveMessage(
          current.id,
          ChatMessage(role: 'assistant', text: text),
        );
        return AgentReply(
          message: text,
          quickReplies: const ['помогло', 'желание осталось'],
          state: TurnState.resolve,
        );
      }
      if (_looksLikeDisagreement(message)) {
        _rejectCurrentAdvice(current);
        current.stage = SessionStage.interviewing;
      }
    } else if (current.stage == SessionStage.awaitingOutcome) {
      if (_looksHelped(message)) {
        const text =
            'Отлично. Зафиксируй результат, чтобы твой персональный AI мог учитывать его в следующих ситуациях.';
        await memory.saveMessage(
          current.id,
          ChatMessage(role: 'assistant', text: text),
        );
        return const AgentReply(message: text, state: TurnState.resolve);
      }
      if (_looksDesireRemains(message)) {
        _rejectCurrentAdvice(current);
        current.stage = SessionStage.interviewing;
      }
    }

    onStage?.call('Уточняю картину');
    final result = await _runInterview(
      credentials: credentials,
      current: current,
      userMessage: message,
    );
    current.applyPatch(result.statePatch);
    if (answeredField != null &&
        directAnswer != null &&
        AgentValidators.isValidFactEntry(answeredField, directAnswer)) {
      current.applyPatch({answeredField: directAnswer});
    }
    if (answeredField == 'last_meal') {
      final inferredMealType = _inferMealType(message);
      if (inferredMealType != null) {
        if ((inferredMealType == 'small_snack' ||
                inferredMealType == 'drink') &&
            result.statePatch['time_since_full_meal_hours'] ==
                result.statePatch['time_since_meal_hours']) {
          current.facts.remove('time_since_full_meal_hours');
        }
        current.applyPatch({'last_meal_type': inferredMealType});
      }
      final mealText = message.toLowerCase();
      if (mealText.contains('только что') ||
          mealText.contains('прямо сейчас')) {
        current.applyPatch({'time_since_meal_hours': .08});
      }
    }
    _pruneInformationPlan(current);
    current.hypotheses
      ..clear()
      ..addAll(result.hypotheses);
    current.missingFields.removeWhere((field) => current.facts[field] != null);

    if (result.readyForAdvice &&
        current.missingFields.isNotEmpty &&
        current.askedFields.length < 5) {
      final field = current.missingFields.firstWhere(
        (item) => !current.askedFields.contains(item),
        orElse: () => '',
      );
      if (field.isNotEmpty) {
        current.askedFields.add(field);
        current.stage = SessionStage.interviewing;
        final question = _fallbackQuestion(field);
        await memory.updateSession(current);
        await memory.saveMessage(
          current.id,
          ChatMessage(role: 'assistant', text: question),
        );
        return AgentReply(
          message: question,
          quickReplies: _fallbackReplies(field),
          state: TurnState.ask,
        );
      }
    }

    if (!result.readyForAdvice) {
      final field = result.nextQuestion.field!;
      current.askedFields.add(field);
      current.stage = SessionStage.interviewing;
      final question = _naturalizeQuestion(
        result.nextQuestion.message,
        answeredField,
        current,
      );
      await memory.updateSession(current);
      await memory.saveMessage(
        current.id,
        ChatMessage(role: 'assistant', text: question),
      );
      return AgentReply(
        message: question,
        quickReplies: result.nextQuestion.quickReplies,
        state: TurnState.ask,
      );
    }

    current.stage = SessionStage.readyForAdvice;
    onStage?.call('Формирую совет');
    final draft = await _runAdvice(credentials: credentials, current: current);
    onStage?.call('Проверяю рекомендацию');
    final reviewed = await _runReview(
      credentials: credentials,
      current: current,
      candidate: draft.candidate,
      requiredCorrection: draft.requiredCorrection,
    );
    current.lastAdvice = reviewed.advice;
    current.stage = SessionStage.awaitingFeedback;
    await memory.updateSession(current);
    final text = '${reviewed.advice.message}\n\n${reviewed.advice.followUp}'
        .trim();
    await memory.saveMessage(
      current.id,
      ChatMessage(role: 'assistant', text: text),
    );
    return AgentReply(
      message: text,
      quickReplies: reviewed.advice.alternatives,
      state: TurnState.advise,
    );
  }

  Future<void> finish({
    required AppCredentials credentials,
    required String outcome,
    StageCallback? onStage,
  }) async {
    final current = state;
    if (current == null || current.lastAdvice == null) return;
    onStage?.call('Сохраняю полезный опыт');
    final draft = await _validated<MemoryDraft>(
      () => memoryAgent.run(
        credentials: credentials,
        state: current,
        userOutcome: outcome,
      ),
      AgentValidators.memory,
    );
    final vector = await client.embed(
      credentials,
      draft.retrievalText,
      document: true,
    );
    await memory.saveDraft(
      sessionId: current.id,
      draft: draft,
      outcome: outcome,
      vector: vector,
    );
    current.stage = SessionStage.completed;
    state = null;
  }

  Future<T> _validated<T>(
    Future<T> Function() call,
    void Function(T value) validate,
  ) async {
    try {
      final value = await call();
      validate(value);
      return value;
    } catch (error) {
      if (error is! AgentValidationException && !_isBrokenJson(error)) {
        rethrow;
      }
      final repaired = await call();
      validate(repaired);
      return repaired;
    }
  }

  Future<({AdviceResult candidate, String? requiredCorrection})> _runAdvice({
    required AppCredentials credentials,
    required CaseState current,
  }) async {
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        final candidate = await advice.run(
          credentials: credentials,
          state: current,
        );
        try {
          AgentValidators.advice(candidate, current);
          return (candidate: candidate, requiredCorrection: null);
        } on AgentValidationException catch (error) {
          // A structurally valid draft is still useful to Review Agent. Passing the
          // exact violation gives the second agent a concrete editing task.
          return (candidate: candidate, requiredCorrection: error.message);
        }
      } catch (error) {
        if (!_isBrokenJson(error) || attempt == 1) rethrow;
      }
    }
    throw StateError('Advice Agent не вернул результат');
  }

  Future<ReviewResult> _runReview({
    required AppCredentials credentials,
    required CaseState current,
    required AdviceResult candidate,
    String? requiredCorrection,
  }) async {
    var latestCandidate = candidate;
    var correction = requiredCorrection;
    Object? latestError;
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        final result = await review.run(
          credentials: credentials,
          state: current,
          candidate: latestCandidate,
          requiredCorrection: correction,
        );
        try {
          AgentValidators.review(result, current);
          return result;
        } on AgentValidationException catch (error) {
          latestError = error;
          correction = error.message;
          latestCandidate = result.advice;
        }
      } catch (error) {
        latestError = error;
        if (!_isBrokenJson(error)) rethrow;
      }
    }
    if (latestError is AgentValidationException &&
        latestError.message.contains('Повторяющаяся потеря контроля')) {
      final repaired = AdviceResult(
        decision: latestCandidate.decision,
        message:
            '${latestCandidate.message} Поскольку это повторяется несколько раз в неделю и вызывает тревогу, стоит обсудить это со специалистом по пищевому поведению или психологом — поддержка здесь уместна, и тебе не обязательно справляться в одиночку.',
        followUp: latestCandidate.followUp,
        episodeSummary: latestCandidate.episodeSummary,
        alternatives: latestCandidate.alternatives,
      );
      AgentValidators.advice(repaired, current);
      return ReviewResult(
        verdict: 'revise',
        advice: repaired,
        violations: const ['Добавлена рекомендация профессиональной поддержки'],
      );
    }
    throw latestError ?? StateError('Review Agent не вернул результат');
  }

  Future<IntakeResult> _runIntake({
    required AppCredentials credentials,
    required String message,
  }) async {
    IntakeResult? latest;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        latest = await intake.run(credentials: credentials, message: message);
        AgentValidators.intake(latest);
        return latest;
      } catch (error) {
        if (error is! AgentValidationException && !_isBrokenJson(error)) {
          rethrow;
        }
        // Повторяем один раз, затем задаём один надёжный локальный вопрос.
      }
    }
    if (latest == null) {
      return IntakeResult(
        request: {'desire': message.trim(), 'category': 'other'},
        knownFacts: const {},
        hypotheses: const [],
        informationPlan: const [
          {'field': 'hunger_level', 'priority': 1},
          {'field': 'last_meal', 'priority': 2},
          {'field': 'time_since_meal_hours', 'priority': 3},
        ],
        firstQuestion: UserQuestion(
          field: 'hunger_level',
          message: _fallbackQuestion('hunger_level'),
          quickReplies: _fallbackReplies('hunger_level'),
        ),
      );
    }
    final knownFacts = <String, dynamic>{};
    for (final entry in latest.knownFacts.entries) {
      if (entry.value != null &&
          AgentValidators.isValidFactEntry(entry.key, entry.value)) {
        knownFacts[entry.key] = entry.value;
      }
    }
    const coreFields = ['hunger_level', 'last_meal', 'time_since_meal_hours'];
    final firstField = coreFields.firstWhere(
      (field) => knownFacts[field] == null,
      orElse: () => 'hunger_level',
    );
    final desire = (latest.request['desire'] as String? ?? '').trim();
    final category =
        const {
          'sweet',
          'fatty',
          'salty',
          'drink',
          'meal',
          'other',
        }.contains(latest.request['category'])
        ? latest.request['category'] as String
        : 'other';
    return IntakeResult(
      request: {
        'desire': desire.isEmpty ? message.trim() : desire,
        'category': category,
      },
      knownFacts: knownFacts,
      hypotheses: latest.hypotheses,
      informationPlan: [
        for (var i = 0; i < coreFields.length; i++)
          {'field': coreFields[i], 'priority': i + 1},
      ],
      firstQuestion: UserQuestion(
        field: firstField,
        message: _fallbackQuestion(firstField),
        quickReplies: _fallbackReplies(firstField),
      ),
    );
  }

  Future<InterviewResult> _runInterview({
    required AppCredentials credentials,
    required CaseState current,
    required String userMessage,
  }) async {
    InterviewResult? latest;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        latest = await interview.run(
          credentials: credentials,
          state: current,
          userMessage: userMessage,
        );
        AgentValidators.interview(latest, current);
        return latest;
      } catch (error) {
        if (error is! AgentValidationException && !_isBrokenJson(error)) {
          rethrow;
        }
        // Повторяем один раз, затем продолжаем через безопасный локальный fallback.
      }
    }
    return _interviewFallback(
      latest ??
          InterviewResult(
            statePatch: const {},
            status: 'needs_clarification',
            nextQuestion: const UserQuestion(message: ''),
            hypotheses: current.hypotheses,
          ),
      current,
      userMessage,
    );
  }

  bool _isBrokenJson(Object error) =>
      error is AliceException && error.message.contains('некорректный JSON');

  Map<String, dynamic> _safeInitialFacts(Map<String, dynamic> facts) {
    const groundedFromDesire = {
      'context',
      'craving_specificity',
      'desired_portion',
    };
    return Map<String, dynamic>.fromEntries(
      facts.entries.where(
        (entry) =>
            groundedFromDesire.contains(entry.key) &&
            entry.value != null &&
            AgentValidators.isValidFactEntry(entry.key, entry.value),
      ),
    );
  }

  InterviewResult _interviewFallback(
    InterviewResult latest,
    CaseState current,
    String userMessage,
  ) {
    final patch = <String, dynamic>{};
    const allowed = {
      'hunger_level',
      'last_meal',
      'last_meal_type',
      'time_since_meal_hours',
      'time_since_full_meal_hours',
      'thirst_level',
      'emotion',
      'energy_level',
      'sleep_quality',
      'context',
      'craving_specificity',
      'desired_portion',
      'would_eat_regular_meal',
      'body_hunger_signals',
    };
    for (final entry in latest.statePatch.entries) {
      if (allowed.contains(entry.key) &&
          entry.value != null &&
          entry.value is! Map &&
          entry.value is! List &&
          AgentValidators.isValidFactEntry(entry.key, entry.value)) {
        patch[entry.key] = entry.value;
      }
    }
    final lastField = current.askedFields.lastOrNull;
    if (lastField != null && patch[lastField] == null) {
      final recovered = _recoverAnswer(lastField, userMessage);
      if (recovered != null) patch[lastField] = recovered;
    }

    if (current.askedFields.length >= 5) {
      return InterviewResult(
        statePatch: patch,
        status: 'ready_for_advice',
        nextQuestion: const UserQuestion(message: ''),
        hypotheses: latest.hypotheses,
      );
    }

    final unresolved = current.missingFields
        .where(
          (field) =>
              AgentValidators.isKnownFactField(field) &&
              current.facts[field] == null &&
              patch[field] == null,
        )
        .toList();
    final mergedFacts = <String, dynamic>{...current.facts, ...patch};
    final mealType = mergedFacts['last_meal_type'];
    if ((mealType == 'small_snack' || mealType == 'drink') &&
        mergedFacts['time_since_full_meal_hours'] == null &&
        !unresolved.contains('time_since_full_meal_hours')) {
      unresolved.insert(0, 'time_since_full_meal_hours');
    }
    final hunger = mergedFacts['hunger_level'];
    final hours = mergedFacts['time_since_meal_hours'];
    if (hunger is num &&
        hunger >= 8 &&
        hours is num &&
        hours <= 3 &&
        mergedFacts['would_eat_regular_meal'] == null &&
        !unresolved.contains('would_eat_regular_meal')) {
      unresolved.insert(0, 'would_eat_regular_meal');
    }
    if (unresolved.isEmpty) {
      return InterviewResult(
        statePatch: patch,
        status: 'ready_for_advice',
        nextQuestion: const UserQuestion(message: ''),
        hypotheses: latest.hypotheses,
      );
    }
    final field = unresolved.firstWhere(
      (item) => !current.askedFields.contains(item),
      orElse: () => '',
    );
    if (field.isEmpty) {
      return InterviewResult(
        statePatch: patch,
        status: 'ready_for_advice',
        nextQuestion: const UserQuestion(message: ''),
        hypotheses: latest.hypotheses,
      );
    }
    return InterviewResult(
      statePatch: patch,
      status: 'needs_clarification',
      nextQuestion: UserQuestion(
        field: field,
        message: _fallbackQuestion(field),
        quickReplies: _fallbackReplies(field),
      ),
      hypotheses: latest.hypotheses,
    );
  }

  Object? _recoverAnswer(String field, String message) {
    final normalized = message.toLowerCase().replaceAll(',', '.');
    final number =
        double.tryParse(
          RegExp(r'\d+(?:\.\d+)?').firstMatch(normalized)?.group(0) ?? '',
        ) ??
        _wordNumber(normalized);
    if (field == 'hunger_level' ||
        field == 'thirst_level' ||
        field == 'energy_level') {
      if (number != null && number >= 0 && number <= 10) return number;
      if (normalized.contains('не особо') ||
          normalized.contains('почти не') ||
          normalized.contains('слабо')) {
        return 2.0;
      }
      if (normalized.contains('голода нет') ||
          normalized.contains('не голоден')) {
        return 0.0;
      }
      if (normalized.contains('средн')) return 5.0;
      if (normalized.contains('очень') || normalized.contains('сильно')) {
        return 9.0;
      }
      return null;
    }
    if (field == 'time_since_meal_hours') {
      if (normalized.contains('ем сейчас') ||
          normalized.contains('ещё не закончил') ||
          normalized.contains('еще не закончил')) {
        return 0.0;
      }
      if (normalized.contains('менее час') ||
          normalized.contains('меньше час')) {
        return .5;
      }
      if (number == null) return null;
      return normalized.contains('минут') ? number / 60 : number;
    }
    if (field == 'time_since_full_meal_hours') {
      if (normalized.contains('менее час') ||
          normalized.contains('меньше час')) {
        return .5;
      }
      if (number == null) return null;
      return normalized.contains('минут') ? number / 60 : number;
    }
    if (field == 'last_meal_type') {
      if (normalized.contains('полноцен') ||
          normalized.contains('обычн') ||
          normalized.contains('обед') ||
          normalized.contains('ужин') ||
          normalized.contains('завтрак')) {
        return 'full_meal';
      }
      if (normalized.contains('перекус') ||
          normalized.contains('немного') ||
          normalized.contains('пару')) {
        return 'small_snack';
      }
      if (normalized.contains('напит') || normalized.contains('выпил')) {
        return 'drink';
      }
      return 'unclear';
    }
    if (field == 'would_eat_regular_meal') {
      if (RegExp(r'(^|\s)(да|скорее да|yes)(\s|$)').hasMatch(normalized)) {
        return true;
      }
      if (RegExp(r'(^|\s)(нет|скорее нет|no)(\s|$)').hasMatch(normalized)) {
        return false;
      }
      return null;
    }
    if (field == 'emotion') {
      if (normalized.contains('стресс')) return 'stress';
      if (normalized.contains('скук')) return 'boredom';
      if (normalized.contains('груст')) return 'sadness';
      if (normalized.contains('тревог')) return 'anxiety';
      if (normalized.contains('спокой')) return 'calm';
      return 'unknown';
    }
    if (field == 'craving_specificity') {
      if (normalized.contains('только') || normalized.contains('именно')) {
        return 'specific';
      }
      if (normalized.contains('люб') || normalized.contains('друг')) {
        return 'flexible';
      }
      return 'unclear';
    }
    if (field == 'body_hunger_signals') {
      if (normalized.contains('нет') || normalized.contains('не чувств')) {
        return 'absent';
      }
      return 'present';
    }
    return message.trim().isEmpty ? null : message.trim();
  }

  String? _inferMealType(String message) {
    final text = message.toLowerCase();
    if (text.contains('перекус') ||
        text.contains('небольш') ||
        text.contains('немного') ||
        text.contains('пару') ||
        text.contains('лёгкий салат') ||
        text.contains('легкий салат') ||
        text.contains('конфет') ||
        text.contains('печень') ||
        text.contains('шоколадк')) {
      return 'small_snack';
    }
    if (text.contains('только кофе') ||
        text.contains('напит') ||
        text.contains('выпил')) {
      return 'drink';
    }
    if (text.contains('полноцен') ||
        text.contains('плотно') ||
        text.contains('обычн') ||
        text.contains('обед') ||
        text.contains('ужин') ||
        text.contains('завтрак')) {
      return 'full_meal';
    }
    return null;
  }

  double? _wordNumber(String text) {
    const numbers = {
      'ноль': 0.0,
      'один': 1.0,
      'два': 2.0,
      'три': 3.0,
      'четыре': 4.0,
      'пять': 5.0,
      'шесть': 6.0,
      'семь': 7.0,
      'восемь': 8.0,
      'девять': 9.0,
      'десять': 10.0,
    };
    for (final entry in numbers.entries) {
      if (RegExp('(^|\\s)${entry.key}(\\s|\$)').hasMatch(text)) {
        return entry.value;
      }
    }
    return null;
  }

  bool _isUnknownAnswer(String message) {
    final text = message.toLowerCase().trim();
    return text.contains('не уверен') ||
        text.contains('не уверена') ||
        text.contains('не знаю') ||
        text.contains('сложно сказать');
  }

  String _naturalizeQuestion(
    String question,
    String? answeredField,
    CaseState current,
  ) {
    final normalized = question.toLowerCase();
    if (const [
      'понял',
      'поняла',
      'хорошо',
      'спасибо',
      'похоже',
      'ясно',
    ].any(normalized.startsWith)) {
      return question;
    }
    String? acknowledgement;
    if (answeredField == 'hunger_level') {
      final hunger = current.facts['hunger_level'];
      if (hunger is num && hunger <= 3) {
        acknowledgement = 'Сильного голода сейчас нет.';
      } else if (hunger is num && hunger >= 7) {
        acknowledgement = 'Голод уже довольно заметный.';
      }
    } else if (answeredField == 'last_meal') {
      acknowledgement = switch (current.facts['last_meal_type']) {
        'small_snack' => 'Это больше похоже на небольшой перекус.',
        'drink' => 'Пока это был только напиток.',
        'full_meal' => 'Хорошо, это был полноценный приём пищи.',
        _ => null,
      };
    } else if (answeredField == 'emotion') {
      acknowledgement = 'Спасибо, что сказал об этом.';
    }
    return acknowledgement == null ? question : '$acknowledgement $question';
  }

  String _fallbackQuestion(String field) => switch (field) {
    'hunger_level' => 'Насколько ты сейчас голоден по шкале от 0 до 10?',
    'last_meal' => 'Что ты ел или пил в последний раз?',
    'last_meal_type' => 'Это был полноценный приём пищи или небольшой перекус?',
    'time_since_meal_hours' =>
      'Сколько времени прошло с последнего приёма пищи?',
    'time_since_full_meal_hours' =>
      'А когда до этого был последний полноценный приём пищи?',
    'thirst_level' => 'Насколько сильно тебе сейчас хочется пить от 0 до 10?',
    'emotion' => 'Что ты сейчас чувствуешь: спокойствие, стресс или скуку?',
    'energy_level' => 'Сколько у тебя сейчас энергии по шкале от 0 до 10?',
    'sleep_quality' => 'Как ты спал прошлой ночью?',
    'context' => 'Что происходило прямо перед желанием перекусить?',
    'craving_specificity' =>
      'Тебе хочется именно этого или подойдёт другая еда?',
    'desired_portion' => 'Какую примерно порцию тебе хочется?',
    'would_eat_regular_meal' =>
      'Если бы желаемой еды не было, ты бы сейчас съел обычный полноценный приём пищи?',
    'body_hunger_signals' =>
      'Есть ли телесные признаки голода — пустота в желудке, слабость или урчание?',
    _ => 'Что происходило прямо перед желанием перекусить?',
  };

  List<String> _fallbackReplies(String field) => switch (field) {
    'hunger_level' || 'thirst_level' || 'energy_level' => ['2', '5', '8'],
    'time_since_meal_hours' => ['меньше часа', '2–3 часа', 'больше 4 часов'],
    'time_since_full_meal_hours' => [
      'меньше 2 часов',
      '3–4 часа',
      'больше 5 часов',
    ],
    'last_meal_type' => ['полноценная еда', 'небольшой перекус', 'напиток'],
    'emotion' => ['спокойствие', 'стресс', 'скука'],
    'would_eat_regular_meal' => ['да', 'скорее да', 'нет'],
    'body_hunger_signals' => ['есть', 'не замечаю', 'не уверен'],
    _ => const [],
  };

  void _pruneInformationPlan(CaseState current) {
    final hunger = current.facts['hunger_level'];
    final hours = current.facts['time_since_meal_hours'];
    final needsRegularMealCheck =
        hunger is num && hunger >= 8 && hours is num && hours <= 3;
    if (!needsRegularMealCheck) {
      current.missingFields.remove('would_eat_regular_meal');
    }

    final mealType = current.facts['last_meal_type'];
    if (mealType == 'full_meal') {
      current.missingFields.remove('time_since_full_meal_hours');
    } else if ((mealType == 'small_snack' || mealType == 'drink') &&
        current.facts['time_since_full_meal_hours'] == null &&
        !current.missingFields.contains('time_since_full_meal_hours')) {
      current.missingFields.add('time_since_full_meal_hours');
    }
  }

  bool _looksLikeDisagreement(String message) {
    final text = message.toLowerCase();
    return [
      'нет',
      'не хочу',
      'не соглас',
      'не подходит',
      'всё равно',
    ].any(text.contains);
  }

  String? _selectedAlternative(CaseState current, String message) {
    final normalized = message.trim().toLowerCase();
    for (final alternative in current.lastAdvice?.alternatives ?? const []) {
      final candidate = alternative.trim().toLowerCase();
      if (normalized == candidate || normalized.contains(candidate)) {
        return alternative;
      }
    }
    return null;
  }

  void _rejectCurrentAdvice(CaseState current) {
    final rejected = current.lastAdvice?.decision;
    if (rejected != null && !current.rejectedAdvice.contains(rejected)) {
      current.rejectedAdvice.add(rejected);
    }
  }

  bool _looksHelped(String message) {
    final text = message.toLowerCase();
    return text.contains('помог') || text.contains('стало легче');
  }

  bool _looksDesireRemains(String message) {
    final text = message.toLowerCase();
    return text.contains('желание осталось') ||
        text.contains('не помог') ||
        text.contains('всё ещё хочу');
  }
}
