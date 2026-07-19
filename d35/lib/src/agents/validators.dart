import 'dart:convert';

import '../models/models.dart';

class AgentValidationException implements Exception {
  const AgentValidationException(this.message);
  final String message;
  @override
  String toString() => message;
}

abstract final class AgentValidators {
  static const factFields = {
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

  static void intake(IntakeResult result) {
    if ((result.request['desire'] as String? ?? '').trim().isEmpty) {
      throw const AgentValidationException('Intake не определил запрос');
    }
    _validateFactPatch(result.knownFacts);
    if (result.firstQuestion.message.isEmpty) {
      throw const AgentValidationException(
        'Intake не сформировал первый вопрос',
      );
    }
    _validateInformalTone(result.firstQuestion.message);
    _validateSingleFieldQuestion(result.firstQuestion);
    final fields = result.informationPlan
        .map((item) => item['field'])
        .whereType<String>()
        .toList();
    if (fields.any((field) => !isKnownFactField(field))) {
      throw const AgentValidationException(
        'Intake добавил неизвестное поле в план уточнений',
      );
    }
    if (fields.toSet().length != fields.length) {
      throw const AgentValidationException('Intake продублировал поля плана');
    }
  }

  static void interview(InterviewResult result, CaseState state) {
    _validateFactPatch(result.statePatch);
    final mergedFacts = <String, dynamic>{
      ...state.facts,
      ...Map<String, dynamic>.fromEntries(
        result.statePatch.entries.where((entry) => entry.value != null),
      ),
    };
    _validateHypotheses(result.hypotheses, mergedFacts);
    if (result.readyForAdvice) {
      final unresolved = state.missingFields
          .where((field) => result.statePatch[field] == null)
          .toList();
      if (_requiresHungerDisambiguation(mergedFacts) &&
          mergedFacts['would_eat_regular_meal'] == null) {
        unresolved.add('would_eat_regular_meal');
      }
      if (unresolved.isNotEmpty) {
        throw AgentValidationException(
          'Interview завершился без обязательных фактов: ${unresolved.join(', ')}',
        );
      }
      if (result.nextQuestion.message.isNotEmpty) {
        throw const AgentValidationException(
          'Готовый случай не должен содержать новый вопрос',
        );
      }
      return;
    }
    if (result.nextQuestion.message.isEmpty ||
        result.nextQuestion.field == null) {
      throw const AgentValidationException(
        'Interview должен задать один вопрос',
      );
    }
    if (state.askedFields.length >= 5) {
      throw const AgentValidationException(
        'Interview превысил лимит уточняющих вопросов',
      );
    }
    _validateInformalTone(result.nextQuestion.message);
    _validateSingleFieldQuestion(result.nextQuestion);
    if (result.nextQuestion.field == 'would_eat_regular_meal' &&
        !_requiresHungerDisambiguation(mergedFacts)) {
      throw const AgentValidationException(
        'Проверка обычной еды задана без противоречивого сигнала голода',
      );
    }
    if (state.askedFields.contains(result.nextQuestion.field)) {
      throw const AgentValidationException(
        'Interview повторил уже заданный вопрос',
      );
    }
  }

  static void advice(AdviceResult result, CaseState state) {
    const decisions = {'eat_meal', 'eat_snack', 'pause', 'hydrate', 'other'};
    if (!decisions.contains(result.decision)) {
      throw const AgentValidationException('Некорректная метка решения');
    }
    if (result.message.length < 60 || result.message.length > 900) {
      throw const AgentValidationException('Некорректная длина совета');
    }
    if (result.message.trim().endsWith('?') &&
        !result.message.substring(0, result.message.length - 1).contains('.')) {
      throw const AgentValidationException(
        'Вместо рекомендации модель вернула только вопрос',
      );
    }
    _validateInformalTone(result.message);
    _validateInformalTone(result.followUp);
    if (result.followUp.trim().isEmpty) {
      throw const AgentValidationException(
        'Совет не содержит вопроса для обратной связи',
      );
    }
    if (_requiresHungerDisambiguation(state.facts) &&
        state.facts['would_eat_regular_meal'] == null) {
      throw const AgentValidationException(
        'Совет сформирован до проверки противоречивого сигнала голода',
      );
    }
    final stateText = jsonEncode(state.toJson()).toLowerCase();
    final hunger = state.facts['hunger_level'];
    final mealHours =
        state.facts['time_since_full_meal_hours'] ??
        state.facts['time_since_meal_hours'];
    final fastingForTests =
        stateText.contains('анализ') && stateText.contains('натощак');
    final prolongedMealGap =
        hunger is num && hunger >= 5 && mealHours is num && mealHours >= 8;
    final strongPhysicalHunger =
        hunger is num &&
        ((hunger >= 7 &&
                ((mealHours is num && mealHours >= 4) ||
                    state.facts['body_hunger_signals'] == 'present')) ||
            prolongedMealGap);
    if (prolongedMealGap && !fastingForTests && result.decision != 'eat_meal') {
      throw const AgentValidationException(
        'После длительного перерыва нужен полноценный приём пищи, не перекус',
      );
    }
    if (strongPhysicalHunger &&
        !fastingForTests &&
        result.decision != 'eat_meal' &&
        result.decision != 'eat_snack') {
      throw const AgentValidationException(
        'При явном физическом голоде первым действием должна быть еда',
      );
    }
    final thirst = state.facts['thirst_level'];
    if (thirst is num &&
        thirst >= 8 &&
        result.decision != 'hydrate' &&
        !result.message.toLowerCase().contains('выпей')) {
      throw const AgentValidationException(
        'Совет проигнорировал выраженную жажду',
      );
    }
    if (result.episodeSummary.isEmpty) {
      throw const AgentValidationException('Нет резюме эпизода');
    }
    final normalized = result.message.toLowerCase();
    final lastMealType = state.facts['last_meal_type'];
    if (lastMealType != 'small_snack' &&
        (normalized.contains('после перекуса') ||
            normalized.contains('с момента перекуса') ||
            normalized.contains('последнего перекуса') ||
            normalized.contains('перекус был'))) {
      throw const AgentValidationException(
        'Неподтверждённый прошлый приём пищи ошибочно назван перекусом',
      );
    }
    final intentionalSocialTreat =
        (stateText.contains('свидан') ||
            stateText.contains('день рождения') ||
            stateText.contains('празднич')) &&
        (stateText.contains('небольш') ||
            stateText.contains('половин') ||
            stateText.contains('на двоих') ||
            stateText.contains('разделить'));
    if (intentionalSocialTreat && result.decision == 'pause') {
      throw const AgentValidationException(
        'Осознанное социальное удовольствие ошибочно объявлено импульсом',
      );
    }
    if (stateText.contains('энергетик') &&
        (normalized.contains('можешь позволить себе') ||
            normalized.contains('можно рассмотреть его употребление') ||
            normalized.contains('можно выпить энергетик') ||
            normalized.contains('можешь его выпить'))) {
      throw const AgentValidationException(
        'Совет без необходимости одобряет энергетик как запасной вариант',
      );
    }
    final uncertainAllergen =
        stateText.contains('орех') &&
        (stateText.contains('не уверен') ||
            stateText.contains('не уверена') ||
            stateText.contains('нет ли') ||
            stateText.contains('неизвестен'));
    if ((stateText.contains('аллерг') || uncertainAllergen) &&
        !(normalized.contains('состав') &&
            (normalized.contains('не ешь') ||
                normalized.contains('не пробуй') ||
                normalized.contains('уточни')))) {
      throw const AgentValidationException(
        'Совет проигнорировал риск пищевой аллергии',
      );
    }
    if (stateText.contains('диабет') &&
        ![
          'глюкоз',
          'сахар',
          'рекомендац',
          'план врача',
        ].any(normalized.contains)) {
      throw const AgentValidationException(
        'Совет при диабете дан без проверки индивидуального плана',
      );
    }
    if (stateText.contains('анализ') &&
        stateText.contains('натощак') &&
        (![
              'уточни',
              'инструкц',
              'лаборатор',
              'врач',
            ].any(normalized.contains) ||
            result.decision == 'eat_meal' ||
            result.decision == 'eat_snack' ||
            normalized.contains('можно съесть') ||
            normalized.contains('выбрать что-то лёгкое') ||
            normalized.contains('выбрать что-то легкое'))) {
      throw const AgentValidationException(
        'До уточнения правил анализов нельзя предлагать еду или напиток',
      );
    }
    if ((stateText.contains('вообще не есть') ||
            stateText.contains('наказать себя')) &&
        !(normalized.contains('не нужно') || normalized.contains('не стоит'))) {
      throw const AgentValidationException(
        'Совет не остановил компенсационное голодание',
      );
    }
    if (stateText.contains('кружится голова') &&
        !['если', 'обратись', 'помощ'].any(normalized.contains)) {
      throw const AgentValidationException(
        'Совет проигнорировал необходимость наблюдать опасный симптом',
      );
    }
    if (stateText.contains('не смогу остановиться') &&
        stateText.contains('несколько раз в неделю') &&
        ![
          'специалист',
          'психолог',
          'врач',
          'поддержк',
        ].any(normalized.contains)) {
      throw const AgentValidationException(
        'Повторяющаяся потеря контроля оставлена без рекомендации поддержки',
      );
    }
    final sourceMessage =
        (state.request['source_message'] as String? ??
                state.request['desire'] as String? ??
                '')
            .toLowerCase();
    if (sourceMessage.startsWith('съел')) {
      if (normalized.contains('желание съесть')) {
        throw const AgentValidationException(
          'Совет ошибочно трактует уже произошедший эпизод как новое желание',
        );
      }
      if (sourceMessage.contains('стыд') &&
          (![
                'стыд',
                'не нужно исправлять',
                'не надо исправлять',
                'не ругай себя',
                'не наказывай себя',
                'ничего компенсировать',
              ].any(normalized.contains) ||
              ((state.facts['hunger_level'] as num?) ?? 0) <= 3 &&
                  (result.decision == 'eat_meal' ||
                      result.decision == 'eat_snack'))) {
        throw const AgentValidationException(
          'Ответ не поддержал пользователя после уже съеденной еды и стыда',
        );
      }
    }
    int firstIndexOf(Iterable<String> fragments) {
      final indices = fragments
          .map(normalized.indexOf)
          .where((index) => index >= 0)
          .toList();
      return indices.isEmpty ? -1 : indices.reduce((a, b) => a < b ? a : b);
    }

    final pauseIndex = firstIndexOf(const [
      'попробуй отвлеч',
      'сделай пауз',
      'подожди',
      'переключись',
    ]);
    final eatingIndex = firstIndexOf(const [
      'поешь',
      'поесть',
      'съешь',
      'съесть',
      'приём пищи',
      'прием пищи',
      'подкрепись',
    ]);
    final startsWithPause =
        pauseIndex >= 0 && (eatingIndex < 0 || pauseIndex < eatingIndex);
    if (startsWithPause && result.decision != 'pause') {
      throw const AgentValidationException(
        'Техническое решение не совпадает с первым предлагаемым действием',
      );
    }
    if (thirst is num &&
        thirst >= 8 &&
        normalized.contains('сначала выпей') &&
        result.decision != 'hydrate') {
      throw const AgentValidationException(
        'Первое действие — восполнение жидкости, decision должен быть hydrate',
      );
    }
    final claimsCertainPhysicalHunger =
        normalized.contains('физическ') &&
        (normalized.contains('действительно') ||
            normalized.contains('точно') ||
            normalized.contains('это не просто') ||
            normalized.contains('признак физического'));
    if (_requiresHungerDisambiguation(state.facts) &&
        claimsCertainPhysicalHunger &&
        !(state.facts['would_eat_regular_meal'] == true &&
            state.facts['body_hunger_signals'] == 'present')) {
      throw const AgentValidationException(
        'Необоснованно категоричный вывод о физическом голоде',
      );
    }
    for (final rejected in state.rejectedAdvice) {
      if (result.decision == rejected ||
          (rejected.length > 5 &&
              normalized.contains(rejected.toLowerCase()))) {
        throw const AgentValidationException('Повторён отвергнутый совет');
      }
    }
    const forbidden = [
      'накажи себя',
      'пропусти следующий приём пищи',
      'вызови рвоту',
    ];
    if (forbidden.any(normalized.contains)) {
      throw const AgentValidationException(
        'Совет содержит запрещённую рекомендацию',
      );
    }
  }

  static void review(ReviewResult result, CaseState state) {
    if (!{'pass', 'revise', 'block'}.contains(result.verdict)) {
      throw const AgentValidationException('Неизвестный verdict Review Agent');
    }
    advice(result.advice, state);
  }

  static void memory(MemoryDraft draft) {
    if (draft.episode.isEmpty || draft.retrievalText.length < 10) {
      throw const AgentValidationException(
        'Memory Agent не сформировал эпизод',
      );
    }
    for (final candidate in draft.memoryCandidates) {
      final confidence = (candidate['confidence'] as num?)?.toDouble() ?? 0;
      if (confidence < 0 || confidence > 1) {
        throw const AgentValidationException('Некорректная уверенность памяти');
      }
      if (candidate['status'] == 'confirmed' && confidence < .9) {
        candidate['status'] = 'candidate';
      }
    }
  }

  static void _validateFactPatch(Map<String, dynamic> patch) {
    if (patch.keys.any((key) => !factFields.contains(key)) ||
        patch.values.any((value) => value is Map || value is List)) {
      throw const AgentValidationException(
        'Факты должны быть плоскими и использовать известные поля',
      );
    }
    final hunger = patch['hunger_level'];
    if (hunger is num && (hunger < 0 || hunger > 10)) {
      throw const AgentValidationException('Голод должен быть от 0 до 10');
    }
    final hours = patch['time_since_meal_hours'];
    if (hours is num && (hours < 0 || hours > 72)) {
      throw const AgentValidationException('Некорректное время после еды');
    }
    final fullMealHours = patch['time_since_full_meal_hours'];
    if (fullMealHours is num && (fullMealHours < 0 || fullMealHours > 72)) {
      throw const AgentValidationException(
        'Некорректное время после полноценного приёма пищи',
      );
    }
    const mealTypes = {'full_meal', 'small_snack', 'drink', 'unclear'};
    final mealType = patch['last_meal_type'];
    if (mealType != null && !mealTypes.contains(mealType)) {
      throw const AgentValidationException(
        'Некорректно распознан тип последнего приёма пищи',
      );
    }
    final lastMeal = patch['last_meal'];
    if (lastMeal is String && _looksLikeDurationOnly(lastMeal)) {
      throw const AgentValidationException(
        'Время после еды ошибочно сохранено как состав приёма пищи',
      );
    }
    const emotions = {
      'calm',
      'stress',
      'boredom',
      'sadness',
      'anxiety',
      'reward',
      'other',
      'unknown',
    };
    final emotion = patch['emotion'];
    if (emotion != null && !emotions.contains(emotion)) {
      throw const AgentValidationException('Некорректно распознана эмоция');
    }
    const specificity = {'specific', 'flexible', 'unclear'};
    final craving = patch['craving_specificity'];
    if (craving != null && !specificity.contains(craving)) {
      throw const AgentValidationException(
        'Некорректно распознана специфичность желания',
      );
    }
  }

  static bool _requiresHungerDisambiguation(Map<String, dynamic> facts) {
    final hunger = facts['hunger_level'];
    final hours = facts['time_since_meal_hours'];
    return hunger is num && hunger >= 8 && hours is num && hours <= 3;
  }

  static void _validateHypotheses(
    List<Map<String, dynamic>> hypotheses,
    Map<String, dynamic> facts,
  ) {
    for (final hypothesis in hypotheses) {
      final confidence = (hypothesis['confidence'] as num?)?.toDouble() ?? 0;
      if (confidence < 0 || confidence > 1) {
        throw const AgentValidationException(
          'Некорректная уверенность гипотезы',
        );
      }
      if (hypothesis['kind'] == 'physical_hunger' &&
          confidence > .75 &&
          _requiresHungerDisambiguation(facts) &&
          facts['would_eat_regular_meal'] != true &&
          facts['body_hunger_signals'] != 'present') {
        throw const AgentValidationException(
          'Уверенность в физическом голоде не подтверждена фактами',
        );
      }
      final hunger = facts['hunger_level'];
      if (hypothesis['kind'] == 'physical_hunger' &&
          hunger is num &&
          hunger <= 3 &&
          confidence > .5) {
        throw const AgentValidationException(
          'Гипотеза физического голода противоречит низкой оценке голода',
        );
      }
    }
  }

  static void _validateInformalTone(String text) {
    final formalAddress = RegExp(
      r'(?<![а-яё])(вы|вам|вас|вами|ваш|ваша|ваше|ваши|вашего|вашему|вашим|вашем)(?![а-яё])',
      caseSensitive: false,
      unicode: true,
    );
    if (formalAddress.hasMatch(text)) {
      throw const AgentValidationException(
        'Агент переключился на формальное обращение',
      );
    }
  }

  static bool isValidFactEntry(String key, Object? value) {
    try {
      _validateFactPatch({key: value});
      return true;
    } on AgentValidationException {
      return false;
    }
  }

  static bool isKnownFactField(String field) => factFields.contains(field);

  static bool _looksLikeDurationOnly(String value) {
    final text = value.toLowerCase().trim();
    return RegExp(
      r'^(около\s+|примерно\s+|где-то\s+)?\d+(?:[.,–—-]\d+)?\s*(?:минут(?:у|ы)?|час(?:а|ов)?|minutes?|hours?)\s*(?:назад|ago)?$',
      caseSensitive: false,
      unicode: true,
    ).hasMatch(text);
  }

  static void _validateSingleFieldQuestion(UserQuestion question) {
    final text = question.message.toLowerCase();
    if (RegExp(r'^[а-яё]', unicode: true).hasMatch(question.message.trim())) {
      throw const AgentValidationException(
        'Вопрос должен начинаться с заглавной буквы',
      );
    }
    if (question.field != null && !isKnownFactField(question.field!)) {
      throw const AgentValidationException(
        'Агент сформировал вопрос о неизвестном поле',
      );
    }
    if (text.contains('что ещё важно знать') ||
        text.contains('что еще важно знать') ||
        text.contains('расскажи подробнее об этой ситуации')) {
      throw const AgentValidationException(
        'Агент сформировал слишком общий вопрос',
      );
    }
    if (question.field == 'time_since_meal_hours' &&
        (text.contains('что было') || text.contains('что ты ел'))) {
      throw const AgentValidationException(
        'Один вопрос пытается выяснить время и состав еды одновременно',
      );
    }
    if (question.field == 'last_meal' &&
        (text.contains('когда') || text.contains('сколько времени'))) {
      throw const AgentValidationException(
        'Один вопрос пытается выяснить состав и время одновременно',
      );
    }
  }
}
