import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// Phones and the web can scan a QR code with the camera (desktop builds cannot).
bool get canScanQr => kIsWeb || defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS;

/// Full-screen camera that returns the first QR code it reads (a ticket, or counts from another ranger's phone).
class ScanPage extends StatefulWidget {
  const ScanPage({super.key, this.title = 'Point at the ticket QR code'});

  final String title;

  @override
  State<ScanPage> createState() => _ScanPageState();
}

class _ScanPageState extends State<ScanPage> {
  bool _done = false;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.title)),
        body: MobileScanner(onDetect: (capture) {
          final v = capture.barcodes.isEmpty ? null : capture.barcodes.first.rawValue;
          if (v != null && !_done) {
            _done = true;
            Navigator.of(context).pop(v);
          }
        }),
      );
}
