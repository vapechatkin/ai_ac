import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path/path.dart' as p;
import 'package:snack_mind/src/agents/orchestrator.dart';
import 'package:snack_mind/src/data/credentials_store.dart';
import 'package:snack_mind/src/data/local_memory.dart';
import 'package:snack_mind/src/models/models.dart';
import 'package:snack_mind/src/services/alice_client.dart';
import 'package:sqflite/sqflite.dart';

class _Scenario {
  const _Scenario(this.name, this.opening, this.answers);

  final String name;
  final String opening;
  final Map<String, String> answers;
}

const _scenarios = <_Scenario>[
  _Scenario('пропущенный обед', 'Хочу бургер, ужасно голоден', {
    'hunger_level': 'Девять из десяти, живот урчит',
    'last_meal': 'Утром была овсянка и яйца',
    'last_meal_type': 'Полноценный завтрак',
    'time_since_meal_hours': 'Около семи часов',
    'body_hunger_signals': 'Да, урчит живот и появилась слабость',
    'would_eat_regular_meal': 'Да, с удовольствием',
  }),
  _Scenario('скука после ужина', 'Хочется шоколада', {
    'hunger_level': 'Почти не голоден, где-то два',
    'last_meal': 'Плотно поужинал пастой и салатом',
    'last_meal_type': 'Это был полноценный ужин',
    'time_since_meal_hours': 'Минут сорок назад',
    'emotion': 'Скорее скучно, листаю сериал',
    'context': 'Сел смотреть сериал и захотелось что-нибудь жевать',
    'craving_specificity': 'Именно шоколада',
  }),
  _Scenario('небольшой перекус вместо еды', 'Хочу что-нибудь сытное', {
    'hunger_level': 'Не особо, примерно три',
    'last_meal': 'Пару кусочков айвы',
    'last_meal_type': 'Это был маленький перекус',
    'time_since_meal_hours': 'Меньше часа',
    'time_since_full_meal_hours': 'Полноценно ел часов шесть назад',
    'emotion': 'Спокоен',
    'context': 'Просто закончил работу',
  }),
  _Scenario('кофе поздно вечером', 'Хочу кофе', {
    'hunger_level': 'Голода нет',
    'last_meal': 'Ужинал рыбой и овощами',
    'last_meal_type': 'Полноценный ужин',
    'time_since_meal_hours': 'Примерно час назад',
    'energy_level': 'Энергии на три из десяти',
    'sleep_quality': 'Спал всего пять часов',
    'thirst_level': 'Пить хочется где-то на пять',
    'context': 'Нужно ещё поработать перед сном',
  }),
  _Scenario('голод после тренировки', 'После тренировки хочу поесть', {
    'hunger_level': 'Восемь, чувствую пустоту в желудке',
    'last_meal': 'Обедал гречкой с курицей',
    'last_meal_type': 'Полноценный обед',
    'time_since_meal_hours': 'Четыре с половиной часа',
    'body_hunger_signals': 'Пустота в желудке и немного слабости',
    'would_eat_regular_meal': 'Да, обычная еда отлично подойдёт',
  }),
  _Scenario('стресс и фастфуд', 'Очень хочу жирный фастфуд', {
    'hunger_level': 'Наверное четыре',
    'last_meal': 'Два часа назад ел суп и хлеб',
    'last_meal_type': 'Полноценный обед',
    'time_since_meal_hours': 'Около двух часов',
    'emotion': 'Сильно нервничаю после сложного созвона',
    'context': 'Только что закончился неприятный рабочий созвон',
    'craving_specificity': 'Хочется именно бургер и картошку',
  }),
  _Scenario('жажда маскируется под перекус', 'Хочу солёных сухариков', {
    'hunger_level': 'Три из десяти',
    'last_meal': 'Недавно был обычный обед',
    'last_meal_type': 'Полноценная еда',
    'time_since_meal_hours': 'Полтора часа',
    'thirst_level': 'Пить хочется сильно, на восемь',
    'context': 'Вернулся с долгой прогулки по жаре',
    'emotion': 'Спокоен',
  }),
  _Scenario('кино и привычка', 'Думаю взять попкорн', {
    'hunger_level': 'Голод на два',
    'last_meal': 'Ужинал совсем недавно',
    'last_meal_type': 'Полноценный ужин',
    'time_since_meal_hours': 'Минут тридцать',
    'context': 'Пришёл в кино, обычно всегда беру попкорн',
    'emotion': 'Настроение хорошее',
    'craving_specificity': 'Можно и без него, просто привычка',
  }),
  _Scenario('недосып и сладкое', 'Мне срочно нужно сладкое', {
    'hunger_level': 'Где-то пять',
    'last_meal': 'Три часа назад ел бутерброд',
    'last_meal_type': 'Скорее небольшой перекус',
    'time_since_meal_hours': 'Три часа',
    'time_since_full_meal_hours':
        'Нормально ел вчера вечером, часов десять назад',
    'energy_level': 'Энергии почти нет, два из десяти',
    'sleep_quality': 'Почти не спал ночью',
    'would_eat_regular_meal': 'Да, поел бы обычную еду',
  }),
  _Scenario('праздничный десерт', 'Хочу кусок торта', {
    'hunger_level': 'Голоден примерно на четыре',
    'last_meal': 'Только что был праздничный ужин',
    'last_meal_type': 'Полноценная и довольно плотная еда',
    'time_since_meal_hours': 'Минут десять',
    'emotion': 'Радостно, у друга день рождения',
    'context': 'Все сейчас будут есть именинный торт',
    'craving_specificity': 'Да, хочу именно попробовать этот торт',
    'desired_portion': 'Небольшой кусок',
  }),
  _Scenario('дорога и настоящий голод', 'Хочу купить хот-дог на заправке', {
    'hunger_level': 'Семь из десяти',
    'last_meal': 'Завтракал сырниками',
    'last_meal_type': 'Полноценный завтрак',
    'time_since_meal_hours': 'Пять часов назад',
    'context': 'Еду в дороге, до дома ещё три часа',
    'would_eat_regular_meal': 'Да, съел бы нормальный обед',
    'body_hunger_signals': 'Живот пустой и урчит',
  }),
  _Scenario('ночная тяга', 'Перед сном хочется чего-нибудь вкусного', {
    'hunger_level': 'Один из десяти',
    'last_meal': 'Два часа назад плотно ужинал',
    'last_meal_type': 'Полноценный ужин',
    'time_since_meal_hours': 'Два часа',
    'emotion': 'Немного тревожно перед завтрашней встречей',
    'context': 'Лежу в кровати и листаю телефон',
    'craving_specificity': 'Неважно что, просто чего-нибудь вкусного',
  }),
  _Scenario('утренний кофе по привычке', 'Хочу вторую чашку кофе', {
    'hunger_level': 'Не голоден',
    'last_meal': 'Только что позавтракал',
    'last_meal_type': 'Полноценный завтрак',
    'time_since_meal_hours': 'Минут двадцать',
    'energy_level': 'Энергии шесть из десяти',
    'sleep_quality': 'Спал нормально',
    'thirst_level': 'Пить почти не хочется',
    'context': 'Всегда беру вторую чашку, когда сажусь работать',
  }),
  _Scenario('грусть и мороженое', 'Хочу большое ведёрко мороженого', {
    'hunger_level': 'Два из десяти',
    'last_meal': 'Недавно поел рис с рыбой',
    'last_meal_type': 'Полноценный приём пищи',
    'time_since_meal_hours': 'Около часа',
    'emotion': 'Мне грустно после ссоры',
    'context': 'Поссорился с близким человеком и сижу один',
    'desired_portion': 'Хочется съесть всё ведёрко',
    'craving_specificity': 'Именно мороженого',
  }),
  _Scenario('обед без аппетита', 'Надо бы пообедать, но не хочется', {
    'hunger_level': 'Голод на три',
    'last_meal': 'Утром был небольшой йогурт',
    'last_meal_type': 'Небольшой перекус',
    'time_since_meal_hours': 'Четыре часа',
    'time_since_full_meal_hours': 'Полноценно ел вчера вечером',
    'energy_level': 'Энергии мало, около четырёх',
    'body_hunger_signals': 'Слабость есть, но живот не урчит',
  }),
  _Scenario('сладкий напиток', 'Хочу большую сладкую газировку', {
    'hunger_level': 'Не голоден, ноль',
    'last_meal': 'Час назад был обед',
    'last_meal_type': 'Полноценный обед',
    'time_since_meal_hours': 'Один час',
    'thirst_level': 'Пить хочется на семь',
    'context': 'Иду по торговому центру и увидел рекламу',
    'craving_specificity': 'Можно любой холодный напиток',
  }),
  _Scenario('офисные печенья', 'Возьму ещё печенье', {
    'hunger_level': 'Два',
    'last_meal': 'Обедал два часа назад',
    'last_meal_type': 'Полноценный обед',
    'time_since_meal_hours': 'Два часа',
    'context': 'Печенье стоит прямо рядом на офисной кухне',
    'emotion': 'Немного скучно',
    'desired_portion': 'Уже съел три, думаю взять четвёртое',
  }),
  _Scenario('солёное после тренировки без голода', 'Хочу чипсов', {
    'hunger_level': 'Три',
    'last_meal': 'После тренировки выпил протеиновый коктейль',
    'last_meal_type': 'Это был напиток',
    'time_since_meal_hours': 'Полчаса',
    'time_since_full_meal_hours': 'Полноценный обед был пять часов назад',
    'thirst_level': 'Пить хочется на шесть',
    'context': 'Только вернулся после тренировки',
  }),
  _Scenario('неопределённое желание', 'Хочу чего-нибудь, сам не знаю чего', {
    'hunger_level': 'Наверное пять',
    'last_meal': 'Три часа назад ел суп',
    'last_meal_type': 'Это был обычный обед',
    'time_since_meal_hours': 'Три часа',
    'emotion': 'Чувствую усталость',
    'energy_level': 'Энергии три',
    'craving_specificity': 'Вообще не знаю, подойдёт разное',
  }),
  _Scenario('осознанный небольшой десерт', 'Хочу одну конфету к чаю', {
    'hunger_level': 'Голода почти нет',
    'last_meal': 'Недавно поужинал',
    'last_meal_type': 'Полноценный ужин',
    'time_since_meal_hours': 'Час назад',
    'emotion': 'Спокоен и просто хочу вкус чая с конфетой',
    'context': 'Сел спокойно выпить чай',
    'desired_portion': 'Ровно одну конфету',
    'craving_specificity': 'Да, одну конкретную конфету',
  }),
];

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'run twenty realistic conversations',
    (_) async {
      final credentials = await CredentialsStore().read();
      expect(credentials, isNotNull, reason: 'На устройстве нет Yandex-ключа');
      final dbPath = p.join(await getDatabasesPath(), 'scenario_lab.db');
      await deleteDatabase(dbPath);
      final memory = LocalMemory(databaseName: 'scenario_lab.db');
      final reports = <Map<String, dynamic>>[];

      for (final scenario in _scenarios) {
        final orchestrator = AgentOrchestrator(
          client: AliceClient(),
          memory: memory,
        );
        final transcript = <Map<String, String>>[
          {'role': 'user', 'text': scenario.opening},
        ];
        Object? failure;
        AgentReply? reply;
        try {
          reply = await orchestrator.send(
            credentials: credentials!,
            message: scenario.opening,
          );
          transcript.add({'role': 'assistant', 'text': reply.message});
          for (
            var turn = 0;
            turn < 9 && reply!.state == TurnState.ask;
            turn++
          ) {
            final field = orchestrator.state!.askedFields.last;
            final answer = scenario.answers[field] ?? 'Не уверен';
            transcript.add({'role': 'user', 'text': answer});
            reply = await orchestrator.send(
              credentials: credentials,
              message: answer,
            );
            transcript.add({'role': 'assistant', 'text': reply.message});
          }
        } catch (error) {
          failure = error;
        }

        final state = orchestrator.state;
        reports.add({
          'name': scenario.name,
          'opening': scenario.opening,
          'completed': reply?.state == TurnState.advise,
          'failure': failure?.toString(),
          'questions': state?.askedFields.length ?? 0,
          'asked_fields': state?.askedFields ?? const [],
          'facts': state?.facts ?? const {},
          'hypotheses': state?.hypotheses ?? const [],
          'advice': state?.lastAdvice?.toJson(),
          'transcript': transcript,
        });
      }

      await File(
        p.join(await getDatabasesPath(), 'scenario_report.json'),
      ).writeAsString(const JsonEncoder.withIndent('  ').convert(reports));
      expect(reports, hasLength(20));
      // Оставляем пакет запущенным, чтобы внешний раннер успел забрать отчёт.
      await Future<void>.delayed(const Duration(minutes: 2));
    },
    timeout: const Timeout(Duration(minutes: 45)),
  );
}
