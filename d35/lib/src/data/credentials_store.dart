import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../models/models.dart';

class CredentialsStore {
  CredentialsStore({FlutterSecureStorage? storage})
    : _storage =
          storage ??
          const FlutterSecureStorage(
            aOptions: AndroidOptions(encryptedSharedPreferences: true),
            iOptions: IOSOptions(
              accessibility: KeychainAccessibility.first_unlock_this_device,
            ),
          );

  static const _apiKey = 'yandex_api_key';
  static const _folderId = 'yandex_folder_id';
  final FlutterSecureStorage _storage;

  Future<bool> hasCredentials() async {
    final values = await Future.wait([
      _storage.read(key: _apiKey),
      _storage.read(key: _folderId),
    ]);
    return values.every((value) => value != null && value.trim().isNotEmpty);
  }

  Future<AppCredentials?> read() async {
    final values = await Future.wait([
      _storage.read(key: _apiKey),
      _storage.read(key: _folderId),
    ]);
    if (values.any((value) => value == null || value.trim().isEmpty)) {
      return null;
    }
    return AppCredentials(apiKey: values[0]!, folderId: values[1]!);
  }

  Future<void> save(AppCredentials credentials) async {
    await Future.wait([
      _storage.write(key: _apiKey, value: credentials.apiKey.trim()),
      _storage.write(key: _folderId, value: credentials.folderId.trim()),
    ]);
  }

  Future<void> clear() => _storage.deleteAll();
}
