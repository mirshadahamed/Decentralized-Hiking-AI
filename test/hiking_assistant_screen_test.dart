import 'dart:async';

import 'package:decentralized_hiking_ai/features/hiking_assistant/models/rag_response.dart';
import 'package:decentralized_hiking_ai/features/hiking_assistant/models/rag_retrieval_result.dart';
import 'package:decentralized_hiking_ai/features/hiking_assistant/presentation/hiking_assistant_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _source = RagRetrievalResult(
  chunkId: 'hidden-chunk-id',
  sourceId: 'hidden-source-id',
  sourceChunkIndex: 0,
  content: 'INTERNAL_CONTEXT_SHOULD_NOT_BE_DISPLAYED',
  categories: 'hypothermia',
  title: 'Cold weather safety',
  organization: 'Downloaded Hiking Knowledge',
  countryContext: 'International',
);

RagResponse _response(RagAnswerMode mode, String answer) {
  return RagResponse(
    answerMode: mode,
    answer: answer,
    context: 'INTERNAL_CONTEXT_SHOULD_NOT_BE_DISPLAYED',
    sources: const [_source],
    fallbackUsed: mode == RagAnswerMode.safeFallback,
  );
}

Widget _screen(HikingAssistantQuery query) {
  return MaterialApp(home: HikingAssistantScreen.forTesting(query: query));
}

Future<void> _tapAskButton(WidgetTester tester) async {
  final askButton = find.byKey(const Key('ask-button'));
  await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -300));
  await tester.pump();
  await tester.tap(askButton);
}

void main() {
  testWidgets('renders offline status, topic selector, and question input', (
    tester,
  ) async {
    await tester.pumpWidget(
      _screen(
        ({required question, required category}) async =>
            _response(RagAnswerMode.localLlmRag, 'Answer'),
      ),
    );

    expect(find.text('Offline Hiking Assistant'), findsOneWidget);
    expect(find.text('Offline knowledge and local AI'), findsOneWidget);
    expect(find.byKey(const Key('topic-selector')), findsOneWidget);
    expect(find.byKey(const Key('question-input')), findsOneWidget);
    expect(find.text('Sri Lanka emergency'), findsWidgets);
  });

  testWidgets('validates an empty question', (tester) async {
    await tester.pumpWidget(
      _screen(
        ({required question, required category}) async =>
            _response(RagAnswerMode.localLlmRag, 'Answer'),
      ),
    );

    await _tapAskButton(tester);
    await tester.pump();

    expect(find.text('Enter a hiking safety question first.'), findsOneWidget);
  });

  testWidgets('shows a loading state and prevents duplicate requests', (
    tester,
  ) async {
    final completer = Completer<RagResponse>();
    var calls = 0;
    await tester.pumpWidget(
      _screen(({required question, required category}) {
        calls += 1;
        return completer.future;
      }),
    );

    await tester.enterText(find.byKey(const Key('question-input')), 'Help me');
    await _tapAskButton(tester);
    await tester.pump();
    await _tapAskButton(tester);
    await tester.pump();

    expect(calls, 1);
    expect(find.text('Finding offline guidance…'), findsOneWidget);

    completer.complete(_response(RagAnswerMode.localLlmRag, 'Safe answer.'));
    await tester.pumpAndSettle();
  });

  testWidgets('renders a successful local answer and human-readable sources', (
    tester,
  ) async {
    String? receivedCategory;
    await tester.pumpWidget(
      _screen(({required question, required category}) async {
        receivedCategory = category;
        return _response(RagAnswerMode.localLlmRag, 'Move to shelter.');
      }),
    );

    await tester.enterText(find.byKey(const Key('question-input')), 'Help me');
    await _tapAskButton(tester);
    await tester.pumpAndSettle();

    expect(receivedCategory, 'general_first_aid');
    expect(find.text('Move to shelter.'), findsOneWidget);
    expect(
      find.text('Downloaded Hiking Knowledge — Cold weather safety'),
      findsOneWidget,
    );
    expect(find.text('INTERNAL_CONTEXT_SHOULD_NOT_BE_DISPLAYED'), findsNothing);
    expect(find.text('hidden-chunk-id'), findsNothing);
  });

  testWidgets(
    'uses Sri Lanka emergency category and renders verified deterministic answers',
    (tester) async {
      String? receivedCategory;
      await tester.pumpWidget(
        _screen(({required question, required category}) async {
          receivedCategory = category;
          return _response(
            RagAnswerMode.verifiedDeterministic,
            '**Verified answer.**',
          );
        }),
      );

      await tester.tap(find.widgetWithText(ActionChip, 'Sri Lanka emergency'));
      await tester.pump();
      await _tapAskButton(tester);
      await tester.pumpAndSettle();

      expect(receivedCategory, 'sri_lanka_emergency');
      expect(find.text('Verified answer.'), findsOneWidget);
      expect(find.text('**Verified answer.**'), findsNothing);
      expect(find.text('Offline guidance'), findsOneWidget);
    },
  );

  testWidgets('renders safe fallback calmly', (tester) async {
    await tester.pumpWidget(
      _screen(
        ({required question, required category}) async => _response(
          RagAnswerMode.safeFallback,
          'I do not have enough verified offline evidence to provide this guidance safely.',
        ),
      ),
    );

    await tester.enterText(find.byKey(const Key('question-input')), 'Help me');
    await _tapAskButton(tester);
    await tester.pumpAndSettle();

    expect(find.text('Limited offline guidance'), findsOneWidget);
    expect(
      find.textContaining('enough verified offline evidence'),
      findsOneWidget,
    );
  });
}
