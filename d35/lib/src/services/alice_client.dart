import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/models.dart';

class AliceException implements Exception {
  const AliceException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

class AliceClient {
  AliceClient({http.Client? httpClient}) : _http = httpClient ?? http.Client();

  static final _chat = Uri.parse(
    'https://ai.api.cloud.yandex.net/v1/chat/completions',
  );
  static final _embeddings = Uri.parse(
    'https://ai.api.cloud.yandex.net/v1/embeddings',
  );
  final http.Client _http;

  Map<String, String> _headers(AppCredentials credentials) => {
    'Authorization': 'Api-Key ${credentials.apiKey}',
    'Content-Type': 'application/json',
    'OpenAI-Project': credentials.folderId,
  };

  Future<http.Response> _postWithNetworkRetry(
    Uri uri, {
    required Map<String, String> headers,
    required String body,
    required Duration timeout,
  }) async {
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        return await _http
            .post(uri, headers: headers, body: body)
            .timeout(timeout);
      } on TimeoutException {
        rethrow;
      } on http.ClientException {
        if (attempt < 2) {
          await Future<void>.delayed(
            Duration(milliseconds: 500 * (attempt + 1)),
          );
        }
      }
    }
    throw AliceException(
      'Не удалось связаться с Yandex. Проверь интернет и попробуй ещё раз',
    );
  }

  Future<void> verify(AppCredentials credentials) async {
    late final http.Response response;
    try {
      response = await _postWithNetworkRetry(
        _chat,
        headers: _headers(credentials),
        body: jsonEncode({
          'model': 'gpt://${credentials.folderId}/aliceai-llm-flash',
          'messages': const [
            {'role': 'user', 'content': 'Ответь одним словом: готово'},
          ],
          'max_completion_tokens': 8,
          'temperature': 0,
        }),
        timeout: const Duration(seconds: 60),
      );
    } on TimeoutException {
      throw const AliceException(
        'Yandex не ответил за 60 секунд. Попробуй ещё раз или смени сеть',
      );
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw AliceException(
        _messageFor(response),
        statusCode: response.statusCode,
      );
    }
  }

  Future<Map<String, dynamic>> completeStructured({
    required AppCredentials credentials,
    required String systemPrompt,
    required Map<String, dynamic> payload,
    required String schemaName,
    required Map<String, dynamic> schema,
    int maxTokens = 500,
    double temperature = .2,
  }) async {
    late final http.Response response;
    try {
      response = await _postWithNetworkRetry(
        _chat,
        headers: _headers(credentials),
        body: jsonEncode({
          'model': 'gpt://${credentials.folderId}/aliceai-llm-flash',
          'messages': [
            {'role': 'system', 'content': systemPrompt},
            {'role': 'user', 'content': jsonEncode(payload)},
          ],
          'response_format': {
            'type': 'json_schema',
            'json_schema': {
              'name': schemaName,
              'strict': true,
              'schema': schema,
            },
          },
          'max_tokens': maxTokens,
          'temperature': temperature,
        }),
        timeout: const Duration(seconds: 60),
      );
    } on TimeoutException {
      throw const AliceException(
        'Yandex не ответил за 60 секунд. Попробуй ещё раз или смени сеть',
      );
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw AliceException(
        _messageFor(response),
        statusCode: response.statusCode,
      );
    }
    try {
      final payload =
          jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      final choices = payload['choices'] as List?;
      final content = choices?.firstOrNull?['message']?['content'];
      if (content is! String || content.trim().isEmpty) {
        throw const FormatException('empty content');
      }
      return Map<String, dynamic>.from(jsonDecode(content) as Map);
    } on FormatException catch (error) {
      throw AliceException('Модель вернула некорректный JSON: $error');
    }
  }

  Future<List<double>?> embed(
    AppCredentials credentials,
    String text, {
    required bool document,
  }) async {
    try {
      final response = await _postWithNetworkRetry(
        _embeddings,
        headers: _headers(credentials),
        body: jsonEncode({
          'model':
              'emb://${credentials.folderId}/text-embeddings-v2-${document ? 'doc' : 'query'}/',
          'input': text,
          'dimensions': 256,
        }),
        timeout: const Duration(seconds: 20),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) return null;
      final payload =
          jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      final vector =
          (payload['data'] as List?)?.firstOrNull?['embedding'] as List?;
      return vector?.map((value) => (value as num).toDouble()).toList();
    } catch (_) {
      return null;
    }
  }

  String _messageFor(http.Response response) {
    final details = _errorDetails(response);
    if (response.statusCode == 401 || response.statusCode == 403) {
      return details ?? 'Ключ или ID каталога не подошли';
    }
    if (response.statusCode == 400) {
      return details ?? 'Yandex отклонил параметры запроса';
    }
    if (response.statusCode == 429) {
      return 'Лимит запросов исчерпан. Попробуй чуть позже';
    }
    return details ??
        'Твой персональный AI сейчас не ответил (${response.statusCode})';
  }

  String? _errorDetails(http.Response response) {
    try {
      final payload =
          jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      final error = payload['error'];
      final message = error is Map ? error['message'] : payload['message'];
      if (message is String && message.trim().isNotEmpty) {
        return 'Yandex: ${message.trim()}';
      }
    } catch (_) {
      // Оставляем понятное сообщение по HTTP-коду.
    }
    return null;
  }
}
