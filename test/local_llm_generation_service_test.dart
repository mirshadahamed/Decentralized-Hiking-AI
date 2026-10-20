import 'package:flutter_test/flutter_test.dart';

import 'package:decentralized_hiking_ai/features/hiking_assistant/services/local_llm_generation_service.dart';

void main() {
  group('LocalLlmGenerationService sanitization', () {
    test('removes a complete think block', () {
      expect(
        LocalLlmGenerationService.sanitizeGeneratedOutput(
          '<think>private reasoning</think>Use a map and stay on the trail.',
        ),
        'Use a map and stay on the trail.',
      );
    });

    test('removes multiline think blocks', () {
      expect(
        LocalLlmGenerationService.sanitizeGeneratedOutput(
          'Before <think>first line\nsecond line</think> After',
        ),
        'Before After',
      );
    });

    test('drops an unterminated think block and its remainder', () {
      expect(
        LocalLlmGenerationService.sanitizeGeneratedOutput(
          'Keep warm. <think>private reasoning continues',
        ),
        'Keep warm.',
      );
    });

    test('preserves normal answers and normalizes whitespace', () {
      expect(
        LocalLlmGenerationService.sanitizeGeneratedOutput(
          '  Move to shelter.\n\nKeep dry.  ',
        ),
        'Move to shelter. Keep dry.',
      );
    });

    test('returns empty output when sanitization removes all content', () {
      expect(
        LocalLlmGenerationService.sanitizeGeneratedOutput(
          '<think>private reasoning</think>',
        ),
        isEmpty,
      );
    });
  });

  group('LocalLlmGenerationService input validation', () {
    test('rejects uninitialized generation', () {
      expect(
        LocalLlmGenerationService.validateGenerationInput(
          question: 'What should I do?',
          context: 'Evidence',
          isInitialized: false,
        ),
        'Local model is not initialized.',
      );
    });

    test('rejects empty question and evidence context', () {
      expect(
        LocalLlmGenerationService.validateGenerationInput(
          question: '  ',
          context: 'Evidence',
          isInitialized: true,
        ),
        'Question is empty.',
      );
      expect(
        LocalLlmGenerationService.validateGenerationInput(
          question: 'What should I do?',
          context: '  ',
          isInitialized: true,
        ),
        'Offline evidence context is empty.',
      );
    });
  });

  group('LocalLlmGenerationService mobile input budget', () {
    test(
      'reduces oversized evidence while preserving instructions and question',
      () {
        final evidence = List.filled(
          1200,
          'transferable safety evidence',
        ).join(' ');
        final prepared = LocalLlmGenerationService.prepareGroundedPrompt(
          question: 'What should a hiker do?',
          context: evidence,
          contextSize: 1024,
          maxTokens: 128,
        );

        expect(prepared.canGenerate, isTrue);
        expect(prepared.evidenceWasTruncated, isTrue);
        expect(prepared.evidence, startsWith('transferable safety evidence'));
        expect(
          prepared.prompt,
          contains('Answer ONLY from the OFFLINE EVIDENCE'),
        );
        expect(prepared.prompt, contains('What should a hiker do?'));
        expect(
          prepared.estimatedPromptTokens,
          lessThanOrEqualTo(prepared.inputTokenBudget),
        );
        expect(prepared.inputTokenBudget, 704);
      },
    );

    test('preserves short evidence unchanged', () {
      const evidence = 'Move to shelter and keep dry.';
      final prepared = LocalLlmGenerationService.prepareGroundedPrompt(
        question: 'What should I do?',
        context: evidence,
        contextSize: 1024,
        maxTokens: 128,
      );

      expect(prepared.canGenerate, isTrue);
      expect(prepared.evidence, evidence);
      expect(prepared.evidenceWasTruncated, isFalse);
    });

    test(
      'impossible context fails before a test generation runner is called',
      () async {
        var generationCalls = 0;
        final service = LocalLlmGenerationService.forTesting(
          contextSize: 256,
          maxTokens: 128,
          generationRunner: ({required prompt, required maxTokens}) async {
            generationCalls += 1;
            return 'This must not be returned.';
          },
        );

        final result = await service.generateGroundedAnswer(
          question: 'What should I do?',
          context: 'Use the available evidence.',
        );

        expect(result.success, isFalse);
        expect(result.error, contains('mobile input budget'));
        expect(generationCalls, 0);
      },
    );

    test(
      'empty evidence fails safely without calling a test generation runner',
      () async {
        var generationCalls = 0;
        final service = LocalLlmGenerationService.forTesting(
          generationRunner: ({required prompt, required maxTokens}) async {
            generationCalls += 1;
            return 'This must not be returned.';
          },
        );

        final result = await service.generateGroundedAnswer(
          question: 'What should I do?',
          context: '   ',
        );

        expect(result.success, isFalse);
        expect(result.error, 'Offline evidence context is empty.');
        expect(generationCalls, 0);
      },
    );

    test(
      'uses bounded prompt and sanitizes a successful test generation',
      () async {
        String? receivedPrompt;
        final service = LocalLlmGenerationService.forTesting(
          generationRunner: ({required prompt, required maxTokens}) async {
            receivedPrompt = prompt;
            return '<think>private reasoning</think>Move to shelter.';
          },
        );

        final result = await service.generateGroundedAnswer(
          question: 'What should I do?',
          context: 'Move to shelter and keep dry.',
        );

        expect(result.success, isTrue);
        expect(result.answer, 'Move to shelter.');
        expect(receivedPrompt, contains('OFFLINE EVIDENCE:'));
        expect(receivedPrompt, contains('QUESTION:'));
      },
    );
  });
}
