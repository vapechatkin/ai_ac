import 'package:flutter/material.dart';

import '../agents/orchestrator.dart';
import '../data/credentials_store.dart';
import '../data/local_memory.dart';
import '../models/models.dart';
import '../services/alice_client.dart';
import '../theme/app_theme.dart';
import '../widgets/glass.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.credentialsStore,
    required this.onDisconnect,
    this.client,
    this.memory,
  });
  final CredentialsStore credentialsStore;
  final VoidCallback onDisconnect;
  final AliceClient? client;
  final LocalMemory? memory;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  late final AliceClient _alice = widget.client ?? AliceClient();
  late final LocalMemory _memory = widget.memory ?? LocalMemory();
  late final AgentOrchestrator _orchestrator = AgentOrchestrator(
    client: _alice,
    memory: _memory,
  );
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<ChatMessage> _messages = [];
  List<String> _quickReplies = const [];
  AppCredentials? _credentials;
  AgentReply? _lastReply;
  String _stageLabel = '';
  bool _sending = false;
  bool _finishing = false;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    _credentials = await widget.credentialsStore.read();
    if (!mounted) return;
    setState(() {
      _messages
        ..clear()
        ..add(
          ChatMessage(
            role: 'assistant',
            text: 'Что тебе сейчас хочется съесть или выпить?',
          ),
        );
      _quickReplies = const ['сладкого', 'кофе', 'что-то сытное'];
      _lastReply = null;
      _stageLabel = '';
    });
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send([String? preset]) async {
    final text = (preset ?? _input.text).trim();
    if (text.isEmpty || _sending || _credentials == null) return;
    _input.clear();
    setState(() {
      _messages.add(ChatMessage(role: 'user', text: text));
      _sending = true;
      _quickReplies = const [];
    });
    _scrollDown();
    try {
      final reply = await _orchestrator.send(
        credentials: _credentials!,
        message: text,
        onStage: (label) {
          if (mounted) setState(() => _stageLabel = label);
        },
      );
      if (!mounted) return;
      setState(() {
        _lastReply = reply;
        _messages.add(ChatMessage(role: 'assistant', text: reply.message));
        _quickReplies = reply.quickReplies;
      });
    } catch (error) {
      if (!mounted) return;
      final message = error is AliceException
          ? 'Не получилось получить ответ от AI. Проверь соединение и попробуй ещё раз.'
          : 'Не удалось корректно обработать запрос. Отправь его ещё раз — начнём с чистой сессии.';
      setState(
        () => _messages.add(ChatMessage(role: 'assistant', text: message)),
      );
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString()),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _sending = false;
          _stageLabel = '';
        });
      }
      _scrollDown();
    }
  }

  Future<void> _finish() async {
    final outcome = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (_) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 4, 24, 36),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Чем закончилась ситуация?',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w800,
                letterSpacing: -.7,
              ),
            ),
            const SizedBox(height: 18),
            for (final item in const [
              ('helped', 'Совет помог'),
              ('ate_consciously', 'Осознанно поел(а)'),
              ('skipped', 'Решил(а) не перекусывать'),
              ('other', 'Пока не знаю'),
            ])
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: FilledButton.tonal(
                  onPressed: () => Navigator.pop(context, item.$1),
                  child: Text(item.$2),
                ),
              ),
          ],
        ),
      ),
    );
    if (outcome == null || !mounted) return;
    setState(() {
      _sending = true;
      _finishing = true;
      _quickReplies = const [];
    });
    final startNew = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _FinishDialog(
        onSave: () =>
            _orchestrator.finish(credentials: _credentials!, outcome: outcome),
      ),
    );
    if (!mounted) return;
    setState(() {
      _sending = false;
      _finishing = false;
      _stageLabel = '';
    });
    if (startNew == true) await _start();
  }

  void _scrollDown() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 320),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _showMemory() async {
    final rows = await _memory.recent();
    if (!mounted) return;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .72,
        maxChildSize: .9,
        builder: (_, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(24, 4, 24, 40),
          children: [
            const Text(
              'Моя история',
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w800,
                letterSpacing: -1,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Эти эпизоды хранятся только на устройстве.',
              style: TextStyle(color: AppColors.muted),
            ),
            const SizedBox(height: 22),
            if (rows.isEmpty) const Text('Пока здесь пусто.'),
            ...rows.map(
              (row) => Container(
                margin: const EdgeInsets.only(bottom: 10),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppColors.canvas,
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Text(
                  row['summary']! as String,
                  style: const TextStyle(height: 1.4),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _disconnect() async {
    await widget.credentialsStore.clear();
    widget.onDisconnect();
  }

  @override
  Widget build(BuildContext context) {
    final canFinish =
        _lastReply != null &&
        {
          TurnState.advise,
          TurnState.resolve,
          TurnState.safety,
        }.contains(_lastReply!.state);
    return Scaffold(
      resizeToAvoidBottomInset: true,
      body: AmbientBackground(
        child: SafeArea(
          bottom: false,
          child: Column(
            children: [
              _Header(onMemory: _showMemory, onDisconnect: _disconnect),
              Expanded(
                child: ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
                  itemCount: _messages.length + (_sending ? 1 : 0),
                  itemBuilder: (_, index) {
                    if (index == _messages.length) {
                      return _TypingBubble(label: _stageLabel);
                    }
                    return _MessageBubble(message: _messages[index]);
                  },
                ),
              ),
              if (_quickReplies.isNotEmpty)
                SizedBox(
                  height: 48,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 18,
                      vertical: 4,
                    ),
                    itemCount: _quickReplies.length,
                    separatorBuilder: (_, _) => const SizedBox(width: 8),
                    itemBuilder: (_, index) => ActionChip(
                      label: Text(_quickReplies[index]),
                      backgroundColor: Colors.white.withValues(alpha: .72),
                      side: BorderSide(
                        color: Colors.white.withValues(alpha: .8),
                      ),
                      onPressed: () => _send(_quickReplies[index]),
                    ),
                  ),
                ),
              if (canFinish)
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 4, 18, 2),
                  child: TextButton.icon(
                    onPressed: _sending || _finishing ? null : _finish,
                    icon: const Icon(Icons.check_rounded),
                    label: const Text('Совет помог — завершить диалог'),
                  ),
                ),
              _Composer(controller: _input, sending: _sending, onSend: _send),
            ],
          ),
        ),
      ),
    );
  }
}

class _FinishDialog extends StatefulWidget {
  const _FinishDialog({required this.onSave});

  final Future<void> Function() onSave;

  @override
  State<_FinishDialog> createState() => _FinishDialogState();
}

class _FinishDialogState extends State<_FinishDialog> {
  bool _saving = true;
  bool _saved = false;

  @override
  void initState() {
    super.initState();
    _save();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _saved = false;
    });
    try {
      await widget.onSave();
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saved = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _saved = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    child: Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.all(22),
      child: GlassPanel(
        opacity: .94,
        child: AnimatedSize(
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutCubic,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 220),
                child: _saving
                    ? const SizedBox(
                        key: ValueKey('saving'),
                        width: 48,
                        height: 48,
                        child: CircularProgressIndicator(strokeWidth: 3),
                      )
                    : Icon(
                        _saved
                            ? Icons.check_circle_rounded
                            : Icons.error_outline_rounded,
                        key: ValueKey(_saved ? 'saved' : 'error'),
                        size: 52,
                        color: _saved
                            ? const Color(0xFF4E8A68)
                            : const Color(0xFFB25B4B),
                      ),
              ),
              const SizedBox(height: 18),
              Text(
                _saving
                    ? 'Запоминаю эту ситуацию'
                    : _saved
                    ? 'Опыт сохранён'
                    : 'Не удалось сохранить опыт',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -.7,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                _saving
                    ? 'AI подводит короткий итог и сохраняет его на устройстве. Это может занять некоторое время.'
                    : _saved
                    ? 'В следующем диалоге SnackPause сможет учесть этот результат.'
                    : 'Диалог остался на экране. Можно повторить сохранение или вернуться к нему.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.muted, height: 1.45),
              ),
              if (_saving) ...[
                const SizedBox(height: 18),
                const LinearProgressIndicator(
                  borderRadius: BorderRadius.all(Radius.circular(8)),
                ),
                const SizedBox(height: 10),
                const Text(
                  'Пожалуйста, не закрывай приложение',
                  style: TextStyle(color: AppColors.muted, fontSize: 12),
                ),
              ] else if (_saved) ...[
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: () => Navigator.pop(context, true),
                  icon: const Icon(Icons.add_comment_rounded),
                  label: const Text('Начать новый диалог'),
                ),
              ] else ...[
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _save,
                    child: const Text('Попробовать снова'),
                  ),
                ),
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Вернуться в диалог'),
                ),
              ],
            ],
          ),
        ),
      ),
    ),
  );
}

class _Header extends StatelessWidget {
  const _Header({required this.onMemory, required this.onDisconnect});
  final VoidCallback onMemory;
  final VoidCallback onDisconnect;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(18, 10, 10, 4),
    child: Row(
      children: [
        SizedBox(
          width: 46,
          height: 46,
          child: Center(
            child: Image.asset(
              'assets/brand/sp-monogram-transparent.png',
              width: 46,
              height: 46,
              fit: BoxFit.contain,
              semanticLabel: 'SnackPause',
            ),
          ),
        ),
        const SizedBox(width: 8),
        const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Сначала спроси себя',
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w800,
                letterSpacing: -.5,
              ),
            ),
            Row(
              children: [
                Icon(Icons.circle, size: 7, color: Color(0xFF4C9A6B)),
                SizedBox(width: 5),
                Text(
                  'Твой персональный AI',
                  style: TextStyle(fontSize: 10, color: AppColors.muted),
                ),
              ],
            ),
          ],
        ),
        const Spacer(),
        IconButton(
          onPressed: onMemory,
          tooltip: 'История',
          icon: const Icon(Icons.auto_awesome_motion_rounded),
        ),
        PopupMenuButton<String>(
          onSelected: (value) {
            if (value == 'disconnect') onDisconnect();
          },
          itemBuilder: (_) => const [
            PopupMenuItem(value: 'disconnect', child: Text('Удалить ключ')),
          ],
        ),
      ],
    ),
  );
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});
  final ChatMessage message;
  @override
  Widget build(BuildContext context) {
    final user = message.role == 'user';
    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * .82,
        ),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 14),
        decoration: BoxDecoration(
          color: user
              ? Colors.white.withValues(alpha: .88)
              : Colors.white.withValues(alpha: .68),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(22),
            topRight: const Radius.circular(22),
            bottomLeft: Radius.circular(user ? 22 : 6),
            bottomRight: Radius.circular(user ? 6 : 22),
          ),
          border: Border.all(
            color: user
                ? AppColors.acid.withValues(alpha: .95)
                : AppColors.ink.withValues(alpha: .07),
            width: user ? 1.5 : 1,
          ),
          boxShadow: [
            BoxShadow(
              color: AppColors.ink.withValues(alpha: .05),
              blurRadius: 18,
              offset: const Offset(0, 7),
            ),
          ],
        ),
        child: Text(
          message.text,
          style: TextStyle(color: AppColors.ink, height: 1.42, fontSize: 15.5),
        ),
      ),
    );
  }
}

class _TypingBubble extends StatelessWidget {
  const _TypingBubble({required this.label});
  final String label;
  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
          if (label.isNotEmpty) ...[
            const SizedBox(width: 10),
            Text(
              label,
              style: const TextStyle(color: AppColors.muted, fontSize: 12),
            ),
          ],
        ],
      ),
    ),
  );
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.sending,
    required this.onSend,
  });
  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;
  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: const BorderRadius.vertical(top: Radius.circular(30)),
    child: Container(
      padding: EdgeInsets.fromLTRB(
        16,
        12,
        12,
        MediaQuery.paddingOf(context).bottom + 12,
      ),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: .64),
        border: Border(
          top: BorderSide(color: Colors.white.withValues(alpha: .8)),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              minLines: 1,
              maxLines: 4,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                hintText: 'Напиши, что думаешь…',
                fillColor: Colors.white70,
                isDense: true,
              ),
              onSubmitted: (_) => onSend(),
            ),
          ),
          const SizedBox(width: 9),
          IconButton.filled(
            onPressed: sending ? null : onSend,
            style: IconButton.styleFrom(
              backgroundColor: AppColors.ink,
              foregroundColor: Colors.white,
              minimumSize: const Size(52, 52),
            ),
            icon: const Icon(Icons.arrow_upward_rounded),
          ),
        ],
      ),
    ),
  );
}
