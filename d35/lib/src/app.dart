import 'package:flutter/material.dart';

import 'data/credentials_store.dart';
import 'screens/chat_screen.dart';
import 'screens/onboarding_screen.dart';
import 'theme/app_theme.dart';

class SnackMindApp extends StatefulWidget {
  const SnackMindApp({super.key});

  @override
  State<SnackMindApp> createState() => _SnackMindAppState();
}

class _SnackMindAppState extends State<SnackMindApp> {
  final _credentials = CredentialsStore();
  late Future<bool> _configured;

  @override
  void initState() {
    super.initState();
    _configured = _credentials.hasCredentials();
  }

  void _refresh() {
    setState(() {
      _configured = _credentials.hasCredentials();
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SnackPause',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: FutureBuilder<bool>(
        future: _configured,
        builder: (context, snapshot) {
          if (!snapshot.hasData) return const _AppLoader();
          return snapshot.data!
              ? ChatScreen(
                  credentialsStore: _credentials,
                  onDisconnect: _refresh,
                )
              : OnboardingScreen(
                  credentialsStore: _credentials,
                  onConnected: _refresh,
                );
        },
      ),
    );
  }
}

class _AppLoader extends StatelessWidget {
  const _AppLoader();

  @override
  Widget build(BuildContext context) => const Scaffold(
    body: Center(child: CircularProgressIndicator(strokeWidth: 2)),
  );
}
