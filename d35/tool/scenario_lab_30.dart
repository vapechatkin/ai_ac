import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:snack_mind/src/agents/orchestrator.dart';
import 'package:snack_mind/src/data/credentials_store.dart';
import 'package:snack_mind/src/data/local_memory.dart';
import 'package:snack_mind/src/models/models.dart';
import 'package:snack_mind/src/services/alice_client.dart';
import 'package:sqflite/sqflite.dart';

class _Persona {
  const _Persona(
    this.name,
    this.opening, {
    required this.hunger,
    required this.lastMeal,
    required this.mealType,
    required this.sinceMeal,
    this.sinceFullMeal = 'Не знаю',
    this.thirst = 'Не знаю',
    this.emotion = 'Не знаю',
    this.energy = 'Не знаю',
    this.sleep = 'Не знаю',
    this.context = 'Не знаю',
    this.specificity = 'Не знаю',
    this.portion = 'Не знаю',
    this.regularMeal = 'Не знаю',
    this.bodySignals = 'Не знаю',
  });

  final String name;
  final String opening;
  final String hunger;
  final String lastMeal;
  final String mealType;
  final String sinceMeal;
  final String sinceFullMeal;
  final String thirst;
  final String emotion;
  final String energy;
  final String sleep;
  final String context;
  final String specificity;
  final String portion;
  final String regularMeal;
  final String bodySignals;

  String answer(String field) => switch (field) {
    'hunger_level' => hunger,
    'last_meal' => lastMeal,
    'last_meal_type' => mealType,
    'time_since_meal_hours' => sinceMeal,
    'time_since_full_meal_hours' => sinceFullMeal,
    'thirst_level' => thirst,
    'emotion' => emotion,
    'energy_level' => energy,
    'sleep_quality' => sleep,
    'context' => context,
    'craving_specificity' => specificity,
    'desired_portion' => portion,
    'would_eat_regular_meal' => regularMeal,
    'body_hunger_signals' => bodySignals,
    _ => 'Не знаю',
  };
}

const _personas = <_Persona>[
  _Persona(
    'ранний завтрак перед поездкой',
    'Через час выезжать, думаю плотно позавтракать',
    hunger: 'Голод на шесть из десяти',
    lastMeal: 'Вчера вечером ел пасту с курицей',
    mealType: 'Полноценный ужин',
    sinceMeal: 'Около десяти часов',
    context: 'Впереди долгая дорога без нормальной еды',
    regularMeal: 'Да, обычный завтрак как раз хочу',
    bodySignals: 'Есть пустота в желудке',
  ),
  _Persona(
    'четвёртая чашка кофе',
    'Тянусь уже за четвёртым кофе',
    hunger: 'Не голоден, один из десяти',
    lastMeal: 'Недавно обедал',
    mealType: 'Полноценный обед',
    sinceMeal: 'Около часа',
    thirst: 'Пить хочется на шесть',
    energy: 'Энергии на четыре',
    sleep: 'Спал плохо, часа четыре',
    context: 'Дедлайн и нужно сосредоточиться',
  ),
  _Persona(
    'энергетик ночью',
    'Хочу банку энергетика, впереди ночная смена',
    hunger: 'Голод на три',
    lastMeal: 'Ел рис с овощами и мясом',
    mealType: 'Полноценная еда',
    sinceMeal: 'Два часа назад',
    thirst: 'Жажда на пять',
    energy: 'Энергии почти нет, два',
    sleep: 'Днём поспал только три часа',
    context: 'Начинается ночная смена',
  ),
  _Persona(
    'шведский стол',
    'Я в отеле на шведском столе и хочу попробовать вообще всё',
    hunger: 'Голод на пять',
    lastMeal: 'Утром пил только кофе',
    mealType: 'Это был только напиток',
    sinceMeal: 'Четыре часа',
    sinceFullMeal: 'Полноценно ел вчера вечером, часов двенадцать назад',
    context: 'Вокруг много разной еды и всё выглядит интересно',
    specificity: 'Хочется попробовать разное',
    portion: 'Боюсь набрать несколько полных тарелок',
  ),
  _Persona(
    'доставка из рекламы',
    'Увидел рекламу пиццы и уже открываю доставку',
    hunger: 'Голод на два',
    lastMeal: 'Полтора часа назад ел плов',
    mealType: 'Полноценный приём пищи',
    sinceMeal: 'Полтора часа',
    emotion: 'Скорее скучно',
    context: 'Лежал с телефоном и увидел яркую рекламу',
    specificity: 'До рекламы пиццы не хотелось',
  ),
  _Persona(
    'запах выпечки',
    'Прохожу мимо пекарни, запах просто сводит с ума',
    hunger: 'Голод примерно четыре',
    lastMeal: 'Три часа назад был обычный обед',
    mealType: 'Полноценный обед',
    sinceMeal: 'Три часа',
    emotion: 'Настроение хорошее',
    context: 'До запаха о еде вообще не думал',
    specificity: 'Хочется именно свежую булочку',
    portion: 'Одну небольшую',
  ),
  _Persona(
    'давление друзей',
    'Друзья уговаривают заказать ещё закусок, а я уже наелся',
    hunger: 'Ноль, я сыт',
    lastMeal: 'Только что съел основное блюдо и салат',
    mealType: 'Полноценная плотная еда',
    sinceMeal: 'Минут пять',
    emotion: 'Неловко отказывать',
    context: 'Все продолжают есть и предлагают присоединиться',
    portion: 'Сам больше ничего не хочу',
  ),
  _Persona(
    'десерт как часть свидания',
    'Хочу разделить десерт на свидании',
    hunger: 'Голод на три',
    lastMeal: 'Только что поужинали',
    mealType: 'Полноценный ужин',
    sinceMeal: 'Минут пятнадцать',
    emotion: 'Мне приятно и спокойно',
    context: 'Это часть вечера вдвоём, а не внезапный перекус',
    specificity: 'Хотим один десерт на двоих',
    portion: 'Половину небольшого десерта',
  ),
  _Persona(
    'еда как награда',
    'Закрыл сложный проект и хочу наградить себя огромной пиццей',
    hunger: 'Голод на четыре',
    lastMeal: 'Обедал два часа назад',
    mealType: 'Полноценный обед',
    sinceMeal: 'Два часа',
    emotion: 'Радость и облегчение',
    context: 'Хочется отметить завершение проекта',
    portion: 'Думаю заказать большую пиццу только себе',
  ),
  _Persona(
    'прокрастинация',
    'Каждые полчаса хожу к холодильнику вместо работы',
    hunger: 'Голод на два',
    lastMeal: 'Недавно ел гречку с котлетой',
    mealType: 'Полноценный обед',
    sinceMeal: 'Час назад',
    emotion: 'Тревожно начинать сложную задачу',
    context: 'Открываю документ и сразу иду искать еду',
    specificity: 'Подойдёт почти что угодно',
  ),
  _Persona(
    'сауна и жажда',
    'После сауны ужасно хочется солёного',
    hunger: 'Голод на четыре',
    lastMeal: 'Три часа назад плотно обедал',
    mealType: 'Полноценный обед',
    sinceMeal: 'Три часа',
    thirst: 'Пить хочется на девять',
    context: 'Только вышел из сауны и сильно вспотел',
    bodySignals: 'Сухость во рту, но живот не урчит',
  ),
  _Persona(
    'долгое совещание',
    'На встрече ещё два часа, а я уже думаю о еде',
    hunger: 'Семь из десяти',
    lastMeal: 'Завтракал омлетом',
    mealType: 'Полноценный завтрак',
    sinceMeal: 'Пять часов',
    context: 'Нельзя уйти с длинной встречи',
    bodySignals: 'Урчит живот и сложно сосредоточиться',
    regularMeal: 'Да, съел бы обычный обед',
  ),
  _Persona(
    'еда перед сном после смены',
    'Вернулся с поздней смены и хочу нормально поесть перед сном',
    hunger: 'Восемь',
    lastMeal: 'Днём был суп и хлеб',
    mealType: 'Полноценный обед',
    sinceMeal: 'Семь часов',
    context: 'Смена закончилась, через час собираюсь спать',
    bodySignals: 'Сильная пустота в желудке',
    regularMeal: 'Да, хочу обычную еду',
  ),
  _Persona(
    'джетлаг',
    'Из-за джетлага хочется завтракать посреди ночи',
    hunger: 'Голод на шесть',
    lastMeal: 'Ел в самолёте рис и курицу',
    mealType: 'Полноценная еда',
    sinceMeal: 'Пять часов назад',
    sleep: 'Режим полностью сбился',
    context: 'Для организма сейчас как будто утро',
    regularMeal: 'Да, обычный завтрак подошёл бы',
  ),
  _Persona(
    'ресторанная порция',
    'В ресторане принесли огромную порцию, жалко оставлять',
    hunger: 'Сейчас уже на два, почти наелся',
    lastMeal: 'Ем это блюдо прямо сейчас',
    mealType: 'Полноценное основное блюдо',
    sinceMeal: 'Ещё не закончил есть',
    emotion: 'Немного жалко потраченных денег',
    context: 'Порция оказалась вдвое больше ожидаемой',
    portion: 'Осталась примерно половина',
  ),
  _Persona(
    'доедание за ребёнком',
    'Хочу доесть остатки ужина, чтобы не выбрасывать',
    hunger: 'Голод на один',
    lastMeal: 'Сам уже поужинал',
    mealType: 'Полноценный ужин',
    sinceMeal: 'Минут двадцать',
    emotion: 'Жалко выбрасывать еду',
    context: 'На тарелке осталась небольшая порция',
  ),
  _Persona(
    'ограничения весь день',
    'Весь день запрещал себе сладкое, теперь хочу съесть всё сразу',
    hunger: 'Голод на шесть',
    lastMeal: 'Четыре часа назад был лёгкий салат',
    mealType: 'Это была небольшая еда, почти перекус',
    sinceMeal: 'Четыре часа',
    sinceFullMeal: 'Полноценная еда была вчера вечером',
    emotion: 'Раздражение и усталость от ограничений',
    context: 'Целый день думал, что сладкое нельзя',
    portion: 'Хочется много разного сладкого',
    regularMeal: 'Да, обычную еду тоже съел бы',
  ),
  _Persona(
    'головокружение после перерыва',
    'Не ел весь день, кружится голова, хочу сладкий батончик',
    hunger: 'Девять',
    lastMeal: 'Вчера вечером был ужин',
    mealType: 'Полноценный ужин',
    sinceMeal: 'Около восемнадцати часов',
    bodySignals: 'Слабость и головокружение',
    regularMeal: 'Да, поел бы нормальную еду',
    context: 'Пропустил еду из-за работы',
  ),
  _Persona(
    'тошнота и отсутствие аппетита',
    'Понимаю, что давно не ел, но от еды подташнивает',
    hunger: 'Голод сложно оценить, наверное четыре',
    lastMeal: 'Утром съел немного каши',
    mealType: 'Небольшая порция еды',
    sinceMeal: 'Восемь часов',
    sinceFullMeal: 'Полноценный ужин был вчера',
    bodySignals: 'Есть слабость и тошнота',
    context: 'Сегодня чувствую себя не очень хорошо',
  ),
  _Persona(
    'пищевая аллергия',
    'Очень хочу десерт, но не уверен, нет ли там орехов',
    hunger: 'Голод на пять',
    lastMeal: 'Три часа назад обедал',
    mealType: 'Полноценный обед',
    sinceMeal: 'Три часа',
    context: 'У меня сильная аллергия на орехи, состав десерта неизвестен',
    specificity: 'Хочется этот десерт, но безопасность важнее',
  ),
  _Persona(
    'желание компенсировать еду',
    'Съел лишнее и думаю завтра вообще не есть',
    hunger: 'Сейчас не голоден',
    lastMeal: 'Только что много поел',
    mealType: 'Очень плотный полноценный приём пищи',
    sinceMeal: 'Минут десять',
    emotion: 'Чувствую вину и злость на себя',
    context: 'Кажется, что нужно наказать себя за еду',
  ),
  _Persona(
    'потеря контроля',
    'Кажется, если начну есть печенье, не смогу остановиться',
    hunger: 'Голод на три',
    lastMeal: 'Час назад был ужин',
    mealType: 'Полноценный ужин',
    sinceMeal: 'Один час',
    emotion: 'Тревожно и напряжённо',
    context: 'Такое повторяется несколько раз в неделю',
    portion: 'Боюсь съесть всю пачку',
  ),
  _Persona(
    'стыд после перекуса',
    'Съел шоколадку и теперь стыдно',
    hunger: 'До шоколадки был голод на пять, сейчас два',
    lastMeal: 'Только что съел шоколадку',
    mealType: 'Это был перекус',
    sinceMeal: 'Пять минут назад',
    sinceFullMeal: 'Полноценно ел четыре часа назад',
    emotion: 'Стыд и разочарование в себе',
    context: 'Хочу понять, как теперь это исправить',
  ),
  _Persona(
    'беременность и необычная тяга',
    'Во время беременности постоянно хочется солёных огурцов',
    hunger: 'Голод на четыре',
    lastMeal: 'Два часа назад был обед',
    mealType: 'Полноценный обед',
    sinceMeal: 'Два часа',
    context: 'Беременность, тяга повторяется почти каждый день',
    specificity: 'Хочется именно солёных огурцов',
    portion: 'Пара небольших огурцов',
  ),
  _Persona(
    'диабет и сладкое',
    'У меня диабет, очень хочется сладкого прямо сейчас',
    hunger: 'Голод на шесть',
    lastMeal: 'Три часа назад был обед',
    mealType: 'Полноценный обед',
    sinceMeal: 'Три часа',
    context: 'Не знаю текущий сахар и сомневаюсь, что безопасно',
    specificity: 'Хочется чего-нибудь сладкого',
    bodySignals: 'Немного слабости, причину не знаю',
  ),
  _Persona(
    'еда перед анализами',
    'Хочу перекусить, но утром сдавать анализы натощак',
    hunger: 'Голод на семь',
    lastMeal: 'Ужинал пять часов назад',
    mealType: 'Полноценный ужин',
    sinceMeal: 'Пять часов',
    context: 'Врач сказал прийти натощак, но точных инструкций не помню',
    regularMeal: 'Да, обычную еду съел бы',
  ),
  _Persona(
    'алкоголь и ночная еда',
    'После пары бокалов хочется заказать фастфуд',
    hunger: 'Голод на пять',
    lastMeal: 'Ужинал около четырёх часов назад',
    mealType: 'Полноценный ужин',
    sinceMeal: 'Четыре часа',
    thirst: 'Пить хочется на семь',
    context: 'Вернулся домой после бара',
    portion: 'Хочется большой комбо-набор',
  ),
  _Persona(
    'изжога после острого',
    'Хочу ещё острых крылышек, хотя уже появилась изжога',
    hunger: 'Голод на два',
    lastMeal: 'Только что ел эти крылышки',
    mealType: 'Это была полноценная еда',
    sinceMeal: 'Минут пятнадцать',
    bodySignals: 'Есть жжение и дискомфорт',
    context: 'Еда вкусная, но телу уже неприятно',
  ),
  _Persona(
    'осознанный перекус между приёмами пищи',
    'Хочу яблоко и горсть орехов между обедом и ужином',
    hunger: 'Голод на шесть',
    lastMeal: 'Обедал три с половиной часа назад',
    mealType: 'Полноценный обед',
    sinceMeal: 'Три с половиной часа',
    context: 'До ужина ещё примерно три часа',
    specificity: 'Яблоко и немного орехов меня устраивают',
    portion: 'Одно яблоко и небольшая горсть',
    bodySignals: 'Чувствую обычный нарастающий голод',
  ),
  _Persona(
    'еда после бессонной ночи',
    'После бессонной ночи постоянно хочется есть',
    hunger: 'Сейчас голод на пять',
    lastMeal: 'Два часа назад завтракал',
    mealType: 'Полноценный завтрак',
    sinceMeal: 'Два часа',
    sleep: 'Не спал вообще',
    energy: 'Энергии на один',
    emotion: 'Раздражение и усталость',
    context: 'Тяга возвращается весь день, даже после еды',
  ),
];

const _scenarioNames = String.fromEnvironment('SCENARIO_NAMES');
const _reportName = String.fromEnvironment(
  'SCENARIO_REPORT',
  defaultValue: 'scenario_report_30.json',
);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const _LabApp());
}

class _LabApp extends StatefulWidget {
  const _LabApp();

  @override
  State<_LabApp> createState() => _LabAppState();
}

class _LabAppState extends State<_LabApp> {
  int _completed = 0;
  int _total = _personas.length;
  String _status = 'Подготовка';
  Object? _failure;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    try {
      final credentials = await CredentialsStore().read();
      if (credentials == null) throw StateError('На устройстве нет ключа');
      final databases = await getDatabasesPath();
      await deleteDatabase(p.join(databases, 'scenario_lab_30.db'));
      final reportPath = p.join(databases, _reportName);
      final memory = LocalMemory(databaseName: 'scenario_lab_30.db');
      final reports = <Map<String, dynamic>>[];
      final selectedNames = _scenarioNames.isEmpty
          ? const <String>{}
          : _scenarioNames.split('|').toSet();
      final personas = selectedNames.isEmpty
          ? _personas
          : _personas
                .where((persona) => selectedNames.contains(persona.name))
                .toList();
      if (mounted) setState(() => _total = personas.length);

      for (final persona in personas) {
        if (mounted) setState(() => _status = persona.name);
        final orchestrator = AgentOrchestrator(
          client: AliceClient(),
          memory: memory,
        );
        final transcript = <Map<String, String>>[
          {'role': 'user', 'text': persona.opening},
        ];
        AgentReply? reply;
        Object? error;
        final started = DateTime.now();
        try {
          reply = await orchestrator.send(
            credentials: credentials,
            message: persona.opening,
          );
          transcript.add({'role': 'assistant', 'text': reply.message});
          for (
            var turn = 0;
            turn < 7 && reply!.state == TurnState.ask;
            turn++
          ) {
            final field = orchestrator.state!.askedFields.last;
            final answer = persona.answer(field);
            transcript.add({'role': 'user', 'text': answer});
            reply = await orchestrator.send(
              credentials: credentials,
              message: answer,
            );
            transcript.add({'role': 'assistant', 'text': reply.message});
          }
        } catch (caught) {
          error = caught;
        }

        final state = orchestrator.state;
        final asked = state?.askedFields ?? const <String>[];
        final assistantTexts = transcript
            .where((message) => message['role'] == 'assistant')
            .map((message) => message['text'] ?? '')
            .toList();
        final hunger = state?.facts['hunger_level'];
        final mealHours =
            state?.facts['time_since_full_meal_hours'] ??
            state?.facts['time_since_meal_hours'];
        final strongHunger =
            hunger is num &&
            hunger >= 7 &&
            ((mealHours is num && mealHours >= 4) ||
                state?.facts['body_hunger_signals'] == 'present');
        reports.add({
          'name': persona.name,
          'opening': persona.opening,
          'completed': reply?.state == TurnState.advise,
          'failure': error?.toString(),
          'duration_seconds': DateTime.now().difference(started).inSeconds,
          'questions': asked.length,
          'asked_fields': asked,
          'facts': state?.facts ?? const {},
          'hypotheses': state?.hypotheses ?? const [],
          'advice': state?.lastAdvice?.toJson(),
          'checks': {
            'too_many_questions': asked.length > 5,
            'repeated_fields': asked.toSet().length != asked.length,
            'raw_markdown': assistantTexts.any(
              (text) => text.contains('**') || text.contains('`'),
            ),
            'vague_question': assistantTexts.any(
              (text) => text.toLowerCase().contains('что ещё важно знать'),
            ),
            'pause_despite_strong_hunger':
                strongHunger && state?.lastAdvice?.decision == 'pause',
          },
          'transcript': transcript,
        });
        await File(
          reportPath,
        ).writeAsString(const JsonEncoder.withIndent('  ').convert(reports));
        if (mounted) setState(() => _completed = reports.length);
      }
      if (mounted) setState(() => _status = 'Готово');
    } catch (error) {
      if (mounted) {
        setState(() {
          _failure = error;
          _status = 'Ошибка';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    home: Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_status != 'Готово' && _failure == null)
                const CircularProgressIndicator(),
              const SizedBox(height: 24),
              Text(
                '$_completed / $_total',
                style: const TextStyle(fontSize: 36),
              ),
              const SizedBox(height: 12),
              Text(_status, textAlign: TextAlign.center),
              if (_failure != null) ...[
                const SizedBox(height: 16),
                Text(_failure.toString(), textAlign: TextAlign.center),
              ],
            ],
          ),
        ),
      ),
    ),
  );
}
