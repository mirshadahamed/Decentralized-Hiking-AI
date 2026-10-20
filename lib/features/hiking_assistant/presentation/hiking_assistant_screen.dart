import 'package:flutter/material.dart';

import '../models/rag_response.dart';
import '../models/rag_retrieval_result.dart';
import '../services/hybrid_rag_service.dart';

typedef HikingAssistantQuery = Future<RagResponse> Function({
  required String question,
});

class HikingAssistantScreen extends StatefulWidget {
  final HikingAssistantQuery _query;
  factory HikingAssistantScreen({
    Key? key,
    required HybridRagService ragService,
  }) => HikingAssistantScreen._(key: key, query: ragService.ask);
  factory HikingAssistantScreen.forTesting({
    Key? key,
    required HikingAssistantQuery query,
  }) => HikingAssistantScreen._(key: key, query: query);
  const HikingAssistantScreen._({super.key, required this._query});
  @override
  State<HikingAssistantScreen> createState() => _HikingAssistantScreenState();
}

class _HikingAssistantScreenState extends State<HikingAssistantScreen> {
  static const _examples = <_ExampleQuestion>[
    _ExampleQuestion(
      'Hypothermia',
      'What should I do if someone shows signs of hypothermia while hiking?',
    ),
    _ExampleQuestion(
      'Snake bite',
      'What should I do if someone is bitten by a snake while hiking?',
    ),
    _ExampleQuestion(
      "I'm lost",
      'What should I do if I become lost while hiking?',
    ),
    _ExampleQuestion(
      'Allergic reaction',
      'What should I do if someone has a severe allergic reaction while hiking?',
    ),
  ];
  final _questionController = TextEditingController();
  bool _isLoading = false;
  String? _validationMessage;
  String? _errorMessage;
  String? _askedQuestion;
  RagResponse? _response;

  @override
  void dispose() {
    _questionController.dispose();
    super.dispose();
  }

  Future<void> _ask() async {
    if (_isLoading) return;
    final question = _questionController.text.trim();
    if (question.isEmpty) {
      setState(
        () => _validationMessage = 'Enter a hiking safety question first.',
      );
      return;
    }
    setState(() {
      _isLoading = true;
      _validationMessage = null;
      _errorMessage = null;
      _response = null;
    });
    try {
      final response = await widget._query(question: question);
      if (!mounted) return;
      setState(() {
        _askedQuestion = question;
        _response = response;
      });
    } catch (_) {
      if (mounted) {
        setState(
          () => _errorMessage =
              'Offline guidance is temporarily unavailable. Please try again.',
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _selectExample(_ExampleQuestion example) {
    if (_isLoading) return;
    setState(() {
      _questionController.text = example.question;
      _validationMessage = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Offline Hiking Assistant')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Semantics(
                label: 'Offline local AI status',
                child: Chip(
                  avatar: Icon(Icons.offline_bolt, color: colorScheme.primary),
                  label: const Text('Offline knowledge and local AI'),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Ask about hiking safety, first aid, weather hazards, navigation and emergencies.',
              ),
              const SizedBox(height: 20),
              Text(
                'Example questions',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _examples
                    .map(
                      (example) => ActionChip(
                        label: Text(example.label),
                        onPressed: _isLoading
                            ? null
                            : () => _selectExample(example),
                      ),
                    )
                    .toList(),
              ),
              const SizedBox(height: 20),
              TextField(
                key: const Key('question-input'),
                controller: _questionController,
                enabled: !_isLoading,
                minLines: 3,
                maxLines: 6,
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(
                  labelText: 'Ask any hiking safety question',
                  hintText: 'Describe what you need help with while hiking.',
                  border: const OutlineInputBorder(),
                  errorText: _validationMessage,
                ),
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                key: const Key('ask-button'),
                onPressed: _isLoading ? null : _ask,
                icon: _isLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.send),
                label: Text(
                  _isLoading
                      ? 'Finding offline guidance…'
                      : 'Ask offline assistant',
                ),
              ),
              if (_errorMessage != null) ...[
                const SizedBox(height: 16),
                _NoticeCard(message: _errorMessage!),
              ],
              if (_response != null) ...[
                const SizedBox(height: 20),
                _AnswerCard(response: _response!, question: _askedQuestion!),
              ],
              const SizedBox(height: 20),
              Text(
                'Offline guidance supports hiking decisions and is not independently clinically validated.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AnswerCard extends StatelessWidget {
  final RagResponse response;
  final String question;
  const _AnswerCard({required this.response, required this.question});
  @override
  Widget build(BuildContext context) {
    final isFallback = response.answerMode == RagAnswerMode.safeFallback;
    final title = isFallback ? 'Limited offline guidance' : 'Offline guidance';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(isFallback ? Icons.info_outline : Icons.hiking),
                const SizedBox(width: 8),
                Text(title, style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 12),
            Text('You', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(question),
            const SizedBox(height: 12),
            Text(
              'Offline Assistant',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 4),
            SelectableText(_removeLightweightMarkdown(response.answer)),
            if (response.sources.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('Sources', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 6),
              ...response.sources.map(_SourceTile.new),
            ],
          ],
        ),
      ),
    );
  }

  static String _removeLightweightMarkdown(String answer) =>
      answer.replaceAllMapped(
        RegExp(r'(\*\*|__)(.+?)\1'),
        (match) => match.group(2)!,
      );
}

class _SourceTile extends StatelessWidget {
  final RagRetrievalResult source;
  const _SourceTile(this.source);
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text('${source.organization} — ${source.title}'),
  );
}

class _NoticeCard extends StatelessWidget {
  final String message;
  const _NoticeCard({required this.message});
  @override
  Widget build(BuildContext context) => Card(
    color: Theme.of(context).colorScheme.errorContainer,
    child: Padding(padding: const EdgeInsets.all(12), child: Text(message)),
  );
}

class _ExampleQuestion {
  final String label;
  final String question;
  const _ExampleQuestion(this.label, this.question);
}
