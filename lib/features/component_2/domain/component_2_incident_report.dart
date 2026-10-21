import 'dart:convert';
import 'dart:typed_data';

class Component2IncidentReport {
  const Component2IncidentReport({
    required this.id,
    required this.incidentType,
    required this.detectedClasses,
    required this.createdAt,
    required this.status,
    required this.photoThumbnail,
    this.notes = '',
    this.location = '',
  });

  final String id;
  final String incidentType;
  final List<String> detectedClasses;
  final DateTime createdAt;
  final String status;
  final Uint8List photoThumbnail;
  final String notes;
  final String location;

  Map<String, Object?> toJson() => {
    'id': id,
    'incidentType': incidentType,
    'detectedClasses': detectedClasses,
    'createdAt': createdAt.toIso8601String(),
    'status': status,
    'photoThumbnail': base64Encode(photoThumbnail),
    'notes': notes,
    'location': location,
  };

  factory Component2IncidentReport.fromJson(Map<String, Object?> json) =>
      Component2IncidentReport(
        id: json['id']! as String,
        incidentType: json['incidentType']! as String,
        detectedClasses: (json['detectedClasses']! as List<Object?>)
            .cast<String>(),
        createdAt: DateTime.parse(json['createdAt']! as String),
        status: json['status']! as String,
        photoThumbnail: base64Decode(json['photoThumbnail']! as String),
        notes: json['notes'] as String? ?? '',
        location: json['location'] as String? ?? '',
      );
}
