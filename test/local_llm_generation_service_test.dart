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
}
