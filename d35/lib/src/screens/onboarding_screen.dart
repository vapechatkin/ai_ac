import 'package:flutter/material.dart';

import '../data/credentials_store.dart';
import '../models/models.dart';
import '../services/alice_client.dart';
import '../theme/app_theme.dart';
import '../widgets/glass.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({
    super.key,
    required this.credentialsStore,
    required this.onConnected,
    this.client,
  });

  final CredentialsStore credentialsStore;
  final VoidCallback onConnected;
  final AliceClient? client;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _page = PageController();
  final _key = TextEditingController();
  final _folder = TextEditingController();
  final _form = GlobalKey<FormState>();
  bool _loading = false;
  bool _hideKey = true;
  int _step = 0;

  @override
  void dispose() {
    _page.dispose();
    _key.dispose();
    _folder.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _loading = true);
    final credentials = AppCredentials(
      apiKey: _key.text.trim(),
      folderId: _folder.text.trim(),
    );
    try {
      await (widget.client ?? AliceClient()).verify(credentials);
      await widget.credentialsStore.save(credentials);
      if (mounted) widget.onConnected();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString()),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _next() {
    setState(() => _step = 1);
    _page.animateToPage(
      1,
      duration: const Duration(milliseconds: 520),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AmbientBackground(
        child: SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 18, 24, 8),
                child: Row(
                  children: [
                    const _Mark(),
                    const Spacer(),
                    Text(
                      '${_step + 1} / 2',
                      style: Theme.of(
                        context,
                      ).textTheme.labelMedium?.copyWith(color: AppColors.muted),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: PageView(
                  controller: _page,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    _Welcome(onNext: _next),
                    _CredentialsForm(
                      formKey: _form,
                      apiKey: _key,
                      folder: _folder,
                      hideKey: _hideKey,
                      loading: _loading,
                      onToggleKey: () => setState(() => _hideKey = !_hideKey),
                      onConnect: _connect,
                      onBack: () {
                        setState(() => _step = 0);
                        _page.previousPage(
                          duration: const Duration(milliseconds: 420),
                          curve: Curves.easeOutCubic,
                        );
                      },
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Mark extends StatelessWidget {
  const _Mark();
  @override
  Widget build(BuildContext context) => Row(
    children: [
      Image.asset(
        'assets/brand/ambient-blobs-sp-icon.png',
        width: 38,
        height: 38,
        fit: BoxFit.contain,
      ),
      const SizedBox(width: 10),
      const Text(
        'SnackPause',
        style: TextStyle(
          fontWeight: FontWeight.w800,
          fontSize: 17,
          letterSpacing: -.5,
        ),
      ),
    ],
  );
}

class _Welcome extends StatelessWidget {
  const _Welcome({required this.onNext});
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(24, 24, 24, 20),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Spacer(),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 8),
          decoration: BoxDecoration(
            color: AppColors.acid,
            borderRadius: BorderRadius.circular(20),
          ),
          child: const Text(
            'ПАУЗА БЕЗ ЗАПРЕТОВ',
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.1,
            ),
          ),
        ),
        const SizedBox(height: 24),
        Text(
          'Пойми, чего\nтебе хочется\nна самом деле.',
          style: Theme.of(context).textTheme.displayMedium?.copyWith(
            fontWeight: FontWeight.w700,
            height: .98,
            letterSpacing: -2.8,
          ),
        ),
        const SizedBox(height: 22),
        Text(
          'AI задаст несколько точных вопросов и поможет выбрать следующий шаг — без калорий, стыда и строгих правил.',
          style: Theme.of(
            context,
          ).textTheme.bodyLarge?.copyWith(color: AppColors.muted, height: 1.55),
        ),
        const Spacer(),
        FilledButton(
          onPressed: onNext,
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(62),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(22),
            ),
          ),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                'Начать',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
              SizedBox(width: 9),
              Icon(Icons.arrow_forward_rounded),
            ],
          ),
        ),
        const SizedBox(height: 12),
      ],
    ),
  );
}

class _CredentialsForm extends StatelessWidget {
  const _CredentialsForm({
    required this.formKey,
    required this.apiKey,
    required this.folder,
    required this.hideKey,
    required this.loading,
    required this.onToggleKey,
    required this.onConnect,
    required this.onBack,
  });
  final GlobalKey<FormState> formKey;
  final TextEditingController apiKey;
  final TextEditingController folder;
  final bool hideKey;
  final bool loading;
  final VoidCallback onToggleKey;
  final VoidCallback onConnect;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: const EdgeInsets.fromLTRB(24, 34, 24, 30),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        IconButton.filledTonal(
          onPressed: onBack,
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        const SizedBox(height: 30),
        Text(
          'Подключим\nтвой AI',
          style: Theme.of(context).textTheme.displaySmall?.copyWith(
            fontWeight: FontWeight.w700,
            height: 1,
            letterSpacing: -2,
          ),
        ),
        const SizedBox(height: 14),
        Text(
          'Ключ остаётся в защищённом хранилище телефона. Запросы оплачиваются в твоём Yandex Cloud.',
          style: Theme.of(
            context,
          ).textTheme.bodyMedium?.copyWith(color: AppColors.muted, height: 1.5),
        ),
        const SizedBox(height: 28),
        GlassPanel(
          child: Form(
            key: formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _FieldLabel(index: '01', title: 'API-ключ'),
                TextFormField(
                  controller: apiKey,
                  obscureText: hideKey,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: InputDecoration(
                    hintText: 'AQVN…',
                    suffixIcon: IconButton(
                      onPressed: onToggleKey,
                      icon: Icon(
                        hideKey
                            ? Icons.visibility_rounded
                            : Icons.visibility_off_rounded,
                      ),
                    ),
                  ),
                  validator: (value) => (value?.trim().length ?? 0) < 12
                      ? 'Вставь полный API-ключ'
                      : null,
                ),
                const SizedBox(height: 22),
                const _FieldLabel(index: '02', title: 'ID каталога'),
                TextFormField(
                  controller: folder,
                  autocorrect: false,
                  decoration: const InputDecoration(hintText: 'b1g…'),
                  validator: (value) => (value?.trim().length ?? 0) < 8
                      ? 'Вставь ID каталога'
                      : null,
                ),
                const SizedBox(height: 10),
                TextButton.icon(
                  onPressed: () => showModalBottomSheet<void>(
                    context: context,
                    showDragHandle: true,
                    builder: (_) => const Padding(
                      padding: EdgeInsets.fromLTRB(24, 8, 24, 40),
                      child: Text(
                        'Открой Yandex AI Studio → создай API-ключ. ID каталога можно скопировать, нажав на название каталога в верхней части экрана.',
                        style: TextStyle(fontSize: 16, height: 1.5),
                      ),
                    ),
                  ),
                  icon: const Icon(Icons.help_outline_rounded, size: 17),
                  label: const Text('Где взять эти данные?'),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 22),
        FilledButton(
          onPressed: loading ? null : onConnect,
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(62),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(22),
            ),
          ),
          child: loading
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Text(
                  'Проверить и подключить',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
        ),
      ],
    ),
  );
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel({required this.index, required this.title});
  final String index;
  final String title;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(left: 4, bottom: 9),
    child: Row(
      children: [
        Text(
          index,
          style: const TextStyle(
            color: AppColors.muted,
            fontSize: 10,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(width: 8),
        Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      ],
    ),
  );
}
