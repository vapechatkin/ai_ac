import 'package:flutter_test/flutter_test.dart';
import 'package:snack_mind/src/agents/validators.dart';
import 'package:snack_mind/src/models/models.dart';

void main() {
  test('intake result creates a compact plan', () {
    final result = IntakeResult.fromJson({
      'request': {'desire': 'кофе', 'category': 'drink'},
      'known_facts': {'hunger_level': null},
      'hypotheses': [
        {
          'kind': 'fatigue',
          'confidence': .6,
          'evidence': ['пользователь хочет кофе'],
        },
      ],
      'information_plan': [
        {'field': 'sleep_quality', 'priority': 1},
      ],
      'first_question': {
        'field': 'sleep_quality',
        'message': 'Как ты спал прошлой ночью?',
        'quick_replies': ['хорошо', 'плохо'],
      },
    });

    AgentValidators.intake(result);
    expect(result.firstQuestion.field, 'sleep_quality');
    expect(result.informationPlan, hasLength(1));
  });

  test('quick replies remove markdown added by the model', () {
    final question = UserQuestion.fromJson({
      'field': 'hunger_level',
      'message': 'Насколько ты голоден?',
      'quick_replies': ['**2**', '`5`', '__8__'],
    });

    expect(question.quickReplies, ['2', '5', '8']);
  });

  test('standalone hunger answer stays a flat fact', () {
    final state = CaseState(id: 'session', askedFields: ['hunger_level']);
    final result = InterviewResult.fromJson({
      'state_patch': {'hunger_level': 10},
      'status': 'ready_for_advice',
      'next_question': {
        'field': null,
        'message': '',
        'quick_replies': <String>[],
      },
      'hypotheses': [
        {
          'kind': 'physical_hunger',
          'confidence': .9,
          'evidence': ['голод 10 из 10'],
        },
      ],
    });

    AgentValidators.interview(result, state);
    state.applyPatch(result.statePatch);
    expect(state.facts['hunger_level'], 10);
    expect(state.facts.containsKey('facts'), isFalse);
  });

  test('interview cannot advise before meal context is known', () {
    final state = CaseState(
      id: 'session',
      askedFields: ['hunger_level'],
      missingFields: ['hunger_level', 'last_meal', 'time_since_meal_hours'],
    );
    final result = InterviewResult.fromJson({
      'state_patch': {'hunger_level': 10},
      'status': 'ready_for_advice',
      'next_question': {
        'field': null,
        'message': '',
        'quick_replies': <String>[],
      },
      'hypotheses': [],
    });

    expect(
      () => AgentValidators.interview(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('recent meal and high hunger require disambiguation', () {
    final state = CaseState(
      id: 'session',
      facts: {
        'last_meal': 'форель, салат и пирог',
        'time_since_meal_hours': 2.5,
      },
    );
    final result = InterviewResult.fromJson({
      'state_patch': {'hunger_level': 9},
      'status': 'ready_for_advice',
      'next_question': {
        'field': null,
        'message': '',
        'quick_replies': <String>[],
      },
      'hypotheses': [
        {
          'kind': 'physical_hunger',
          'confidence': .7,
          'evidence': ['голод 9 из 10'],
        },
      ],
    });

    expect(
      () => AgentValidators.interview(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('food craving cannot be stored as an emotion', () {
    final result = InterviewResult.fromJson({
      'state_patch': {'emotion': 'желание съесть вкусного'},
      'status': 'needs_clarification',
      'next_question': {
        'field': 'hunger_level',
        'message': 'Насколько ты сейчас голоден?',
        'quick_replies': <String>[],
      },
      'hypotheses': [],
    });

    expect(
      () => AgentValidators.interview(result, CaseState(id: 'session')),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('meal time cannot be stored as meal contents', () {
    final result = InterviewResult.fromJson({
      'state_patch': {
        'last_meal': '2–3 часа назад',
        'time_since_meal_hours': 2.5,
      },
      'status': 'needs_clarification',
      'next_question': {
        'field': 'hunger_level',
        'message': 'Насколько ты сейчас голоден?',
        'quick_replies': <String>[],
      },
      'hypotheses': [],
    });

    expect(
      () => AgentValidators.interview(result, CaseState(id: 'session')),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('one question cannot request two different facts', () {
    final result = IntakeResult.fromJson({
      'request': {'desire': 'нутелла', 'category': 'sweet'},
      'known_facts': <String, dynamic>{},
      'hypotheses': <Map<String, dynamic>>[],
      'information_plan': [
        {'field': 'time_since_meal_hours', 'priority': 1},
      ],
      'first_question': {
        'field': 'time_since_meal_hours',
        'message': 'Когда ты ел и что было в том приёме пищи?',
        'quick_replies': <String>[],
      },
    });

    expect(
      () => AgentValidators.intake(result),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('intake rejects a vague question without a clear answer target', () {
    final result = IntakeResult.fromJson({
      'request': {'desire': 'перекусить', 'category': 'other'},
      'known_facts': <String, dynamic>{},
      'hypotheses': <Map<String, dynamic>>[],
      'information_plan': [
        {'field': 'context', 'priority': 1},
      ],
      'first_question': {
        'field': 'context',
        'message': 'Что ещё важно знать об этой ситуации?',
        'quick_replies': <String>[],
      },
    });

    expect(
      () => AgentValidators.intake(result),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('intake rejects unknown fields in its information plan', () {
    final result = IntakeResult.fromJson({
      'request': {'desire': 'перекусить', 'category': 'other'},
      'known_facts': <String, dynamic>{},
      'hypotheses': <Map<String, dynamic>>[],
      'information_plan': [
        {'field': 'something_else', 'priority': 1},
      ],
      'first_question': {
        'field': 'hunger_level',
        'message': 'Насколько ты сейчас голоден по шкале от 0 до 10?',
        'quick_replies': <String>[],
      },
    });

    expect(
      () => AgentValidators.intake(result),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('pause recommendation must use pause decision', () {
    const result = AdviceResult(
      decision: 'eat_snack',
      message:
          'Сначала попробуй отвлечься на небольшую разминку на 15–20 минут. После этого снова оцени своё желание.',
      followUp: 'Изменилось ли желание после паузы?',
      episodeSummary: 'Низкий голод и скука.',
    );

    expect(
      () => AgentValidators.advice(result, CaseState(id: 'session')),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('strong physical hunger cannot be delayed with a pause', () {
    final state = CaseState(
      id: 'session',
      facts: {
        'hunger_level': 8,
        'time_since_full_meal_hours': 5,
        'body_hunger_signals': 'present',
      },
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'Сделай паузу на десять минут и выпей воды, а затем снова проверь, действительно ли тебе хочется есть.',
      followUp: 'Изменилось ли желание после паузы?',
      episodeSummary: 'Сильный голод после длительного перерыва.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('a pause after eating is not mistaken for the first action', () {
    final state = CaseState(
      id: 'session',
      facts: {'hunger_level': 7, 'time_since_full_meal_hours': 10},
    );
    const result = AdviceResult(
      decision: 'eat_meal',
      message:
          'Сейчас поешь нормальную сытную еду. После приёма пищи сделай небольшую паузу и оцени насыщение.',
      followUp: 'Удалось ли спокойно поесть?',
      episodeSummary: 'Выраженный голод после долгого перерыва.',
    );

    AgentValidators.advice(result, state);
  });

  test('prolonged restriction cannot be treated as an emotional craving', () {
    final state = CaseState(
      id: 'session',
      request: {'desire': 'хочу съесть всё сладкое'},
      facts: {'hunger_level': 6, 'time_since_full_meal_hours': 12},
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'Попробуй отвлечься на пятнадцать минут и проверить, останется ли желание сладкого после небольшой паузы.',
      followUp: 'Стало ли желание слабее?',
      episodeSummary: 'Длительное ограничение еды и тяга к сладкому.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('a snack is insufficient after a prolonged full-meal gap', () {
    final state = CaseState(
      id: 'session',
      facts: {'hunger_level': 6, 'time_since_full_meal_hours': 24},
    );
    const result = AdviceResult(
      decision: 'eat_snack',
      message:
          'Съешь фрукт или йогурт, а затем оцени, уменьшилось ли желание сладкого после лёгкого перекуса.',
      followUp: 'Стало ли легче?',
      episodeSummary: 'Голод после суток без полноценной еды.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('unknown allergen cannot be ignored in advice', () {
    final state = CaseState(
      id: 'session',
      request: {'desire': 'хочу десерт, но у меня аллергия на орехи'},
      facts: {'hunger_level': 5, 'context': 'состав десерта неизвестен'},
    );
    const result = AdviceResult(
      decision: 'eat_snack',
      message:
          'Если хочется десерт, можешь взять небольшую порцию и съесть её медленно, обращая внимание на вкус и насыщение.',
      followUp: 'Подходит ли тебе небольшая порция?',
      episodeSummary: 'Желание десерта при неизвестном составе.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('original wording keeps an uncertain allergen visible', () {
    final state = CaseState(
      id: 'session',
      request: {
        'desire': 'десерт',
        'source_message': 'Очень хочу десерт, но не уверен, нет ли там орехов',
      },
      facts: {'hunger_level': 5, 'time_since_meal_hours': 3},
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'Сделай небольшую паузу и через десять минут проверь, осталось ли желание съесть этот десерт.',
      followUp: 'Изменилось ли желание?',
      episodeSummary: 'Желание десерта после недавней еды.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('diabetes requires an individual safety check', () {
    final state = CaseState(
      id: 'session',
      request: {'desire': 'у меня диабет и хочется сладкого'},
      facts: {'hunger_level': 6, 'body_hunger_signals': 'present'},
    );
    const result = AdviceResult(
      decision: 'eat_snack',
      message:
          'Можешь позволить себе немного сладкого и затем проверить, стало ли тебе лучше после небольшого перекуса.',
      followUp: 'Стало ли тебе лучше?',
      episodeSummary: 'Слабость и желание сладкого при диабете.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('compensation by fasting must be challenged directly', () {
    final state = CaseState(
      id: 'session',
      request: {'desire': 'съел лишнее и завтра хочу вообще не есть'},
      facts: {'emotion': 'other'},
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'Сделай паузу и отвлекись, чтобы эмоции после плотного приёма пищи немного утихли и стало спокойнее.',
      followUp: 'Стало ли спокойнее?',
      episodeSummary: 'Вина после еды и желание компенсировать.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('strong thirst cannot be ignored', () {
    final state = CaseState(
      id: 'session',
      facts: {'hunger_level': 3, 'thirst_level': 9},
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'Отвлекись на десять минут и проверь, останется ли желание солёного после небольшой паузы.',
      followUp: 'Изменилось ли желание?',
      episodeSummary: 'Сильная жажда и желание солёного.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('intentional shared dessert should not be pathologized', () {
    final state = CaseState(
      id: 'session',
      request: {'desire': 'разделить десерт на свидании'},
      facts: {
        'context': 'приятное свидание',
        'desired_portion': 'половина небольшого десерта на двоих',
      },
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'Лучше отвлекись от десерта на пятнадцать минут и проверь, не исчезнет ли желание после разговора.',
      followUp: 'Стало ли желание слабее?',
      episodeSummary: 'Запланированный общий десерт на свидании.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('source message is enough to recognize a shared social dessert', () {
    final state = CaseState(
      id: 'session',
      request: {
        'desire': 'десерт',
        'source_message': 'Хочу разделить десерт на свидании',
      },
      facts: {'hunger_level': 3, 'time_since_meal_hours': .25},
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'Откажись от десерта сейчас и отвлекись на разговор на пятнадцать минут, чтобы желание прошло.',
      followUp: 'Удалось ли отказаться?',
      episodeSummary: 'Общий десерт на свидании после ужина.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('fasting lab instructions override generic strong-hunger rule', () {
    final state = CaseState(
      id: 'session',
      request: {
        'desire': 'перекусить',
        'source_message': 'Хочу перекусить, но утром анализы натощак',
      },
      facts: {'hunger_level': 7, 'time_since_meal_hours': 5},
    );
    const result = AdviceResult(
      decision: 'other',
      message:
          'Не решай вслепую: проверь инструкцию к анализам или уточни в лаборатории, когда именно начинается период натощак.',
      followUp: 'Удалось ли найти точную инструкцию?',
      episodeSummary:
          'Голод перед анализами с неизвестными правилами подготовки.',
    );

    AgentValidators.advice(result, state);
  });

  test('fasting labs cannot receive a provisional food recommendation', () {
    final state = CaseState(
      id: 'session',
      request: {'source_message': 'Хочу перекусить, но утром анализы натощак'},
      facts: {'hunger_level': 7, 'time_since_meal_hours': 5},
    );
    const result = AdviceResult(
      decision: 'eat_meal',
      message:
          'Выбери что-то лёгкое, а если сомневаешься, потом уточни правила подготовки в лаборатории.',
      followUp: 'Получилось ли выбрать еду?',
      episodeSummary: 'Голод перед анализами натощак.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('energy drink cannot be approved after a snack', () {
    final state = CaseState(
      id: 'session',
      request: {'source_message': 'Хочу энергетик перед ночной сменой'},
      facts: {'hunger_level': 3, 'time_since_meal_hours': 2},
    );
    const result = AdviceResult(
      decision: 'eat_snack',
      message:
          'Сначала перекуси чем-то сытным, а если усталость останется, можешь его выпить и продолжить смену.',
      followUp: 'Стало ли больше энергии?',
      episodeSummary: 'Желание энергетика перед ночной сменой.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('shame after eaten food cannot be reframed as another snack', () {
    final state = CaseState(
      id: 'session',
      request: {'source_message': 'Съел шоколадку и теперь стыдно'},
      facts: {'hunger_level': 2, 'time_since_meal_hours': .1},
    );
    const result = AdviceResult(
      decision: 'eat_snack',
      message:
          'Теперь выбери фрукт или йогурт, чтобы насытиться и снизить вероятность следующего спонтанного перекуса.',
      followUp: 'Какой продукт тебе больше нравится?',
      episodeSummary: 'Стыд после шоколадки.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('ambiguous hunger cannot receive a categorical conclusion', () {
    final state = CaseState(
      id: 'session',
      facts: {
        'hunger_level': 9,
        'last_meal': 'форель, салат и пирог',
        'time_since_meal_hours': 2.5,
        'would_eat_regular_meal': false,
      },
    );
    const result = AdviceResult(
      decision: 'eat_meal',
      message:
          'Это действительно признак физического голода. Можешь съесть бургер и не сомневаться в своём выборе.',
      followUp: 'Насколько тебе подходит этот вариант?',
      episodeSummary: 'Сильный голод вскоре после еды.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('unknown meal type must be called a meal, not a snack', () {
    final state = CaseState(
      id: 'session',
      facts: {
        'hunger_level': 2,
        'last_meal': 'ел три часа назад',
        'last_meal_type': 'unclear',
        'time_since_meal_hours': 3,
      },
    );
    const result = AdviceResult(
      decision: 'pause',
      message:
          'После перекуса прошло три часа, поэтому отвлекись ненадолго и проверь своё желание ещё раз.',
      followUp: 'Изменилось ли желание?',
      episodeSummary: 'Желание сладкого через три часа после еды.',
    );

    expect(
      () => AgentValidators.advice(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('interview validator rejects nested facts from the failed dialogue', () {
    final state = CaseState(id: 'session');
    final result = InterviewResult.fromJson({
      'state_patch': {
        'facts': {'last_meal': 'стейк лосося и жирный салат'},
      },
      'status': 'ready_for_advice',
      'next_question': {
        'field': null,
        'message': '',
        'quick_replies': <String>[],
      },
      'hypotheses': [],
    });

    expect(
      () => AgentValidators.interview(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test(
    'advice validator rejects a question without an actual recommendation',
    () {
      final result = AdviceResult(
        decision: 'eat_snack',
        message: 'Какой из предложенных вариантов вам больше подходит сейчас?',
        followUp: 'Что выберете?',
        episodeSummary: 'Пользователь хотел жирную пищу.',
      );

      expect(
        () => AgentValidators.advice(result, CaseState(id: 'session')),
        throwsA(isA<AgentValidationException>()),
      );
    },
  );

  test('agent responses cannot switch from ты to вы', () {
    final result = AdviceResult(
      decision: 'eat_snack',
      message:
          'Если вы действительно голодны, выберите небольшой сытный перекус и спокойно поешьте без спешки.',
      followUp: 'Как вам такой вариант?',
      episodeSummary: 'Пользователь хотел перекусить.',
    );

    expect(
      () => AgentValidators.advice(result, CaseState(id: 'session')),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('interview validator rejects repeated question', () {
    final state = CaseState(id: 'session', askedFields: ['hunger_level']);
    final result = InterviewResult.fromJson({
      'state_patch': {},
      'status': 'needs_clarification',
      'next_question': {
        'field': 'hunger_level',
        'message': 'Насколько ты голоден?',
        'quick_replies': [],
      },
      'hypotheses': [],
    });

    expect(
      () => AgentValidators.interview(result, state),
      throwsA(isA<AgentValidationException>()),
    );
  });

  test('memory validator demotes weak confirmed fact', () {
    final draft = MemoryDraft.fromJson({
      'episode': {'summary': 'Пользователь хотел кофе вечером.'},
      'retrieval_text': 'Желание кофе вечером',
      'memory_candidates': [
        {
          'type': 'pattern',
          'text': 'Вечером хочется кофе',
          'confidence': .6,
          'status': 'confirmed',
        },
      ],
      'do_not_store': [],
    });

    AgentValidators.memory(draft);
    expect(draft.memoryCandidates.single['status'], 'candidate');
  });
}
