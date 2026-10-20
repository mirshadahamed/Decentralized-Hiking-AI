import copy
import unittest
from datetime import datetime, timezone

from sajana.src.route_advisory import suggest_alternative


class RouteAdvisoryTests(unittest.TestCase):
    def setUp(self):
        # Fictional topology for algorithm tests; never a dataset or real navigation route.
        self.now=datetime(2026,10,20,12,tzinfo=timezone.utc)
        self.graph={'graph_id':'test-only','source_reference':'unit-test fixture',
                    'nodes':[{'id':n,'lat':i/100,'lon':0} for i,n in enumerate('ABCD')],
                    'edges':[{'id':name,'from':a,'to':b,'length_m':length,'bidirectional':True,
                              'permitted':True,'geometry_reviewed':True}
                             for name,a,b,length in [('ab','A','B',10),('bd','B','D',10),('ac','A','C',20),('cd','C','D',20)]]}
        self.obs={'observation_id':'obs','hazard_id':'hazard','edge_id':'bd','kind':'rock',
                  'review_state':'reviewed','reviewer_id':'test-reviewer','edge_match_reviewed':True,
                  'reviewed_at':'2026-10-20T11:00:00+00:00','expires_at':'2026-10-20T13:00:00+00:00',
                  'route_relation':'on_trail','blockage':'blocked'}

    def call(self,observations=None):
        return suggest_alternative(self.graph,['ab','bd'],'A','D',[self.obs] if observations is None else observations,self.now)

    def test_confirmed_blockage_returns_existing_connected_alternative(self):
        r=self.call();self.assertEqual(r['status'],'candidate_marked_alternative')
        self.assertEqual(r['route']['edge_ids'],['ac','cd']);self.assertEqual(r['route']['distance_m'],40)
        self.assertFalse(r['route_is_safety_certified']);self.assertIsNone(r['visible_bypass'])

    def test_litter_detection_alone_cannot_close_a_trail(self):
        r=self.call([{'kind':'litter','confidence':0.98,'edge_id':'bd','observation_id':'litter-only'}])
        self.assertEqual(r['status'],'review_required');self.assertIsNone(r['route'])

    def test_rock_beside_trail_does_not_trigger_rerouting(self):
        self.obs['route_relation']='beside_trail'
        self.assertEqual(self.call()['status'],'no_confirmed_blockage')

    def test_expired_or_unlocated_photo_requires_review(self):
        self.obs['expires_at']='2026-10-20T11:59:59+00:00'
        self.assertEqual(self.call()['status'],'review_required')
        self.obs['expires_at']='2026-10-20T13:00:00+00:00';self.obs['edge_match_reviewed']=False
        self.assertEqual(self.call()['status'],'review_required')

    def test_no_alternative_is_fabricated_when_access_is_restricted(self):
        self.graph['edges'][2]['permitted']=False
        self.assertEqual(self.call()['status'],'no_mapped_alternative')

    def test_directed_edges_and_unreviewed_geometry_are_respected(self):
        self.graph['edges'][2].update({'from':'C','to':'A','bidirectional':False})
        self.assertEqual(self.call()['status'],'no_mapped_alternative')
        self.graph['edges'][2].update({'from':'A','to':'C','geometry_reviewed':False})
        self.assertEqual(self.call()['status'],'no_mapped_alternative')

    def test_missing_graph_and_invalid_costs_do_not_create_a_route(self):
        self.assertEqual(suggest_alternative(None,[],'A','D',[],self.now)['status'],'insufficient_route_context')
        for length in (-1,float('nan')):
            self.graph['edges'][2]['length_m']=length
            with self.assertRaises(ValueError):self.call()

    def test_new_review_can_clear_same_hazard_without_clearing_other_hazards(self):
        cleared=dict(self.obs,observation_id='new',reviewed_at='2026-10-20T11:30:00+00:00',blockage='clear')
        self.assertEqual(self.call([self.obs,cleared])['status'],'no_confirmed_blockage')
        other=dict(self.obs,hazard_id='other',observation_id='other')
        self.assertEqual(self.call([self.obs,cleared,other])['status'],'candidate_marked_alternative')


if __name__=='__main__':unittest.main()
