import 'package:flutter/material.dart';

import '../models/rag_response.dart';
import '../models/rag_retrieval_result.dart';
import '../services/hybrid_rag_service.dart';

typedef HikingAssistantQuery = Future<RagResponse> Function({
  required String question,
  required String category,
});

class HikingAssistantScreen extends StatefulWidget {
  final HikingAssistantQuery _query;

  factory HikingAssistantScreen({
    Key? key,
    required HybridRagService ragService,
  }) {
    return HikingAssistantScreen._(key: key, query: ragService.prepare);
  }

  /// Narrow presentation seam used by widget tests; production callers inject
  /// an already configured [HybridRagService] through the main constructor.
  factory HikingAssistantScreen.forTesting({
    Key? key,
    required HikingAssistantQuery query,
  }) {
    return HikingAssistantScreen._(key: key, query: query);
  }

  const HikingAssistantScreen._({super.key, required this._query});

  @override
  State<HikingAssistantScreen> createState() => _HikingAssistantScreenState();
}

class _HikingAssistantScreenState extends State<HikingAssistantScreen> {
  static const _topics = <_SafetyTopic>[
    _SafetyTopic(
      label: 'General first aid',
      category: 'general_first_aid',
      question:
          'What basic first aid steps should I follow when a hiker is injured?',
    ),
    _SafetyTopic(
      label: 'Hypothermia',
      category: 'hypothermia',
      question: 'What should I do if a hiker shows signs of hypothermia?',
    ),
    _SafetyTopic(
      label: 'Severe allergic reaction',
      category: 'allergic_reaction',
      question: 'What should I do if a hiker has a severe allergic reaction?',
    ),
    _SafetyTopic(
      label: 'Lost or disoriented',
      category: 'lost_navigation',
      question: 'What should I do if I am lost on a hiking trail?',
    ),
    _SafetyTopic(
      label: 'Heat illness',
      category: 'heat_illness',
      question: 'What should I do if a hiker develops heat illness?',
    ),
    _SafetyTopic(
      label: 'Sri Lanka emergency',
      category: 'sri_lanka_emergency',
      question: 'How can I request an emergency ambulance in Sri Lanka?',
    ),
  ];

  final _questionController = TextEditingController();
  String _selectedCategory = _topics.first.category;
  bool _isLoading = false;
  String? _validationMessage;
  String? _errorMessage;
  RagResponse? _response;

  @override
  void dispose() {
    _questionController.dispose();
    super.dispose();
  }

  Future<void> _ask() async {
    if (_isLoading) {
      return;
    }

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
      final response = await widget._query(
        question: question,
        category: _selectedCategory,
      );
      if (!mounted) {
        return;
      }
      setState(() => _response = response);
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _errorMessage =
            'Offline guidance is temporarily unavailable. Please try again.';
      });
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  void _selectTopic(_SafetyTopic topic) {
    if (_isLoading) {
      return;
    }
    setState(() {
      _selectedCategory = topic.category;
      _questionController.text = topic.question;
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
                'Guidance is generated from downloaded offline hiking knowledge.',
              ),
              const SizedBox(height: 20),
              Text(
                'Safety topic',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                key: const Key('topic-selector'),
                initialValue: _selectedCategory,
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  labelText: 'Select a topic',
                ),
                items: _topics
                    .map(
                      (topic) => DropdownMenuItem(
                        value: topic.category,
                        child: Text(topic.label),
                      ),
                    )
                    .toList(),
                onChanged: _isLoading
                    ? null
                    : (category) {
                        if (category != null) {
                          setState(() => _selectedCategory = category);
                        }
                      },
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _topics.skip(1).map((topic) {
                  return ActionChip(
                    label: Text(topic.label),
                    onPressed: _isLoading ? null : () => _selectTopic(topic),
                  );
                }).toList(),
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
                  labelText: 'Your hiking safety question',
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
                _NoticeCard(message: _errorMessage!, isError: true),
              ],
              if (_response != null) ...[
                const SizedBox(height: 20),
                _AnswerCard(response: _response!),
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

  const _AnswerCard({required this.response});

  @override
  Widget build(BuildContext context) {
    final isFallback = response.answerMode == RagAnswerMode.safeFallback;
    final title = isFallback ? 'Limited offline guidance' : 'Offline guidance';
    final displayAnswer = _removeLightweightMarkdown(response.answer);

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
            SelectableText(displayAnswer),
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

  /// Presentation-only cleanup for emphasis markers that a local model may
  /// emit. The underlying RAG response remains unchanged.
  static String _removeLightweightMarkdown(String answer) {
    return answer.replaceAllMapped(
      RegExp(r'(\*\*|__)(.+?)\1'),
      (match) => match.group(2)!,
    );
  }
}

class _SourceTile extends StatelessWidget {
  final RagRetrievalResult source;

  const _SourceTile(this.source);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text('${source.organization} — ${source.title}'),
    );
  }
}

class _NoticeCard extends StatelessWidget {
  final String message;
  final bool isError;

  const _NoticeCard({required this.message, required this.isError});

  @override
  Widget build(BuildContext context) {
    final color = isError
        ? Theme.of(context).colorScheme.errorContainer
        : Theme.of(context).colorScheme.surfaceContainerHighest;
    return Card(
      color: color,
      child: Padding(padding: const EdgeInsets.all(12), child: Text(message)),
    );
  }
}

class _SafetyTopic {
  final String label;
  final String category;
  final String question;

  const _SafetyTopic({
    required this.label,
    required this.category,
    required this.question,
  });
}
