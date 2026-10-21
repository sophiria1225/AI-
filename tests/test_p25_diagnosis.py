import unittest

from diagnose_p25_public_traces import compare_csv, export_counts, photos


class P25DiagnosisTests(unittest.TestCase):
    def test_duplicates_do_not_hide_missing_rows_or_unknown_metadata(self):
        result=compare_csv('Title,Artists\nOne,A\nOne,A\n', {1:('One','A'),2:('Two','B')},{1,2,3})
        self.assertEqual(result['missing_known_pairs'],1)
        self.assertEqual(result['duplicate_rows'],1)
        self.assertEqual(result['observed_ids_without_metadata'],1)
        self.assertFalse(result['all_observed_ids_have_metadata'])

    def test_retains_failed_export_and_rewrite_in_order(self):
        rows=[dict(id='s1',name='spotify__show_song_library',args={},
                   data=[dict(song_id=1,title='One',artists=[{'name':'A'}])]),
              dict(id='s2',name='file_system__create_file',args={'content':'incorrect'},data=None),
              dict(id='s3',name='file_system__update_file',args={'content':'Title,Artists\nOne,A\n'},data={'message':'updated'})]
        result=export_counts(rows)
        self.assertEqual(len(result['writes']),2)
        self.assertEqual(result['writes'][0]['status'],'different_csv_header')
        self.assertFalse(result['writes'][0]['json_message_receipt'])
        self.assertEqual(result['writes'][1]['missing_known_pairs'],0)

    def test_different_directory_listings_are_not_merged_into_task_scope(self):
        rows=[dict(id='s1',name='file_system__show_directory',args={},data=['/photos/a']),
              dict(id='s2',name='file_system__show_file',args={'file_path':'~/photos/a'},data={'path':'/photos/a'}),
              dict(id='s3',name='file_system__move_file',args={'source_file_path':'~/photos/a'},data={'message':'moved'}),
              dict(id='s4',name='file_system__show_directory',args={},data=['/archive/a','/unrelated'])]
        result=photos(rows)
        self.assertEqual([r['paths_with_move_receipt'] for r in result['directory_snapshots']],[1,0])
        self.assertEqual(result['read_paths_without_move_receipt'],0)


if __name__=='__main__': unittest.main()
