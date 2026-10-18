import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../widgets/c4_ui.dart';
import 'advisory_officer_home.dart';
import 'halfway_screen.dart';
import 'officer_home.dart';
import 'ranger_home.dart';

/// Login for park staff (rangers, officers, admins). Visitors never need an account.
class StaffLoginScreen extends StatefulWidget {
  const StaffLoginScreen({super.key, this.advisory = false});

  final bool advisory; // pilgrim site: staff work the halfway checks

  @override
  State<StaffLoginScreen> createState() => _StaffLoginScreenState();
}

class _StaffLoginScreenState extends State<StaffLoginScreen> {
  final _user = TextEditingController(), _pass = TextEditingController();
  String? _error;
  bool _busy = false, _hide = true;

  Future<void> _login() async {
    final api = C4Scope.of(context);
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final s = await api.login(_user.text.trim(), _pass.text);
      _pass.clear();
      if (!mounted) return;
      final Widget home = widget.advisory
          ? (s.isOfficer ? const AdvisoryOfficerHome() : const HalfwayScreen())
          : (s.isOfficer ? const OfficerHome() : const RangerHome());
      await Navigator.of(context).pushReplacement(c4Route(context, home));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _user.dispose();
    _pass.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Staff login')),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: ListView(shrinkWrap: true, padding: const EdgeInsets.all(24), children: [
              const Icon(Icons.badge_outlined, size: 56),
              const SizedBox(height: 8),
              Text('Rangers and park officers', textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 24),
              TextField(
                controller: _user,
                autofillHints: const [AutofillHints.username],
                decoration: const InputDecoration(labelText: 'Username', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _pass,
                obscureText: _hide,
                autofillHints: const [AutofillHints.password],
                onSubmitted: (_) => _login(),
                decoration: InputDecoration(
                  labelText: 'Password',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_hide ? Icons.visibility : Icons.visibility_off),
                    tooltip: _hide ? 'Show password' : 'Hide password',
                    onPressed: () => setState(() => _hide = !_hide),
                  ),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ],
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _login,
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                child: _busy ? const CircularProgressIndicator() : const Text('Log in'),
              ),
              const SizedBox(height: 12),
              const BasisNote('Accounts are created by the park administrator. 5 wrong passwords lock the account for 15 minutes.'),
            ]),
          ),
        ),
      );
}
