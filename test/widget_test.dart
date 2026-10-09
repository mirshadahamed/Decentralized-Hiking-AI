import 'package:decentralized_hiking_ai/app/app.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('displays the starter application', (WidgetTester tester) async {
    await tester.pumpWidget(const HikingAssistantApp());

    expect(
      find.text('AI Hiking Assistant and Emergency Coordination System'),
      findsOneWidget,
    );
  });
}
