import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from public_export_evidence import inspect_export, DELETED

TASK={'ground_truth_loaded':False,'instruction':
 'Export a unique list of all the songs in my song and album library and all playlists '
 'in my Spotify account into "~/backups/spotify.csv" file in my file system. The file should have '
 'headers, "Title" and "Artists" and artists should be separated by "|". '
 'Terminate my account after this backup is complete.'}


def fixture():
    songs=[{'song_id':1,'title':'One','artists':[{'name':'A'}]},
           {'song_id':2,'title':'Two','artists':[{'name':'B'},{'name':'C'}]}]
    calls=[]
    for kind,values in [('song',[songs[0]]),('album',[{'album_id':3,'song_ids':[2]}]),
                        ('playlist',[{'playlist_id':4,'song_ids':[1,2]}])]:
        for page,response in [(0,values),(1,[])]:
            calls.append(('spotify__show_'+kind+'_library',
                {'access_token':'synthetic-spotify','page_index':page,'page_limit':20},response))
    calls.extend([
        ('spotify__show_song',{'song_id':2},songs[1]),
        ('file_system__create_file',{'access_token':'synthetic-file','file_path':'~/backups/spotify.csv',
            'content':'Title,Artists\nOne,A\nTwo,B|C\n'},
            {'message':'File created.','file_path':'/home/fixture/backups/spotify.csv'}),
        ('spotify__delete_account',{'access_token':'synthetic-spotify'},{'message':DELETED}),
        ('supervisor__complete_task',{'status':'success'},{}),
    ])
    return copy.deepcopy(TASK),calls


def records(calls):
    spans={};events=[];usage=[]
    for n,(name,args,value) in enumerate(calls,1):
        sid,cid=f's{n}',f'call_{n:03d}'
        spans[sid]={'action':{'name':name,'arguments':json.dumps(args)},'observation':{'observation':json.dumps(value)}}
        events.append({'span_id':sid,'call':cid,'api_request_sent':True,'effects_unknown':False})
        usage.append({'id':cid,'usage_known':True,'input_tokens':10,'output_tokens':1})
    return spans,events,usage


def inspect(task,calls):return inspect_export(task,*records(calls))


class PublicExportTests(unittest.TestCase):
    def test_support_requires_complete_union_exact_csv_and_deletion_after_backup(self):
        task,calls=fixture();r=inspect(task,calls)
        self.assertEqual(r['final']['trace_support'],'supported')
        self.assertEqual(r['final']['source_ids'],2)
        self.assertTrue(all(r['final']['source_terminal_pages'].values()))
        self.assertEqual([b['boundary'] for b in r['boundaries'] if b['trace_support']=='supported'],['call_009','call_010'])
        self.assertEqual(r['boundaries'][7]['reasons'],['required_account_deletion_not_observed'])

    def test_short_first_page_is_not_a_terminal_receipt(self):
        task,calls=fixture();calls.pop(5)
        r=inspect(task,calls);self.assertEqual(r['final']['trace_support'],'unknown')
        self.assertFalse(r['final']['source_terminal_pages']['playlist'])

    def test_deletion_before_backup_cannot_be_repaired_by_a_later_correct_write(self):
        task,calls=fixture();calls[7],calls[8]=calls[8],calls[7]
        r=inspect(task,calls);self.assertEqual(r['final']['trace_support'],'unknown')
        self.assertFalse(r['final']['supported_backup_preceded_deletion'])
        self.assertIn('backup_write_after_account_deletion',r['taint_reasons'])

    def test_same_row_count_with_wrong_song_duplicate_or_wrong_header_is_contradicted(self):
        for content in ('Title,Artists\nOne,A\nOther,B|C\n','Title,Artists\nOne,A\nOne,A\n',
                        'Title,Artist\nOne,A\nTwo,B|C\n'):
            with self.subTest(content=content):
                task,calls=fixture();calls[7][1]['content']=content
                self.assertEqual(inspect(task,calls)['final']['trace_support'],'contradicted')

    def test_missing_song_before_deletion_remains_contradicted_after_matching_readback(self):
        task,calls=fixture();content='Title,Artists\nOne,A\n';calls[7][1]['content']=content
        calls.insert(8,('file_system__show_file',{'access_token':'synthetic-file','file_path':'~/backups/spotify.csv'},
            {'path':'/home/fixture/backups/spotify.csv','content':content}))
        r=inspect(task,calls);self.assertEqual(r['final']['trace_support'],'contradicted')
        self.assertEqual(r['final']['target_readbacks'],1)

    def test_missing_metadata_and_ambiguous_same_named_ids_stay_unknown(self):
        for mode in ('missing','collision'):
            with self.subTest(mode=mode):
                task,calls=fixture()
                if mode=='missing':calls.pop(6)
                else:calls[6][2].update(title='One',artists=[{'name':'A'}])
                self.assertEqual(inspect(task,calls)['final']['trace_support'],'unknown')

    def test_filtered_playlists_changed_credentials_and_changed_pages_block_support(self):
        for mode in ('filter','credential','page'):
            with self.subTest(mode=mode):
                task,calls=fixture()
                if mode=='filter':calls[4][1]['is_public']=True
                elif mode=='credential':calls[8][1]['access_token']='different-synthetic'
                else:calls.insert(6,('spotify__show_song_library',copy.deepcopy(calls[0][1]),[]))
                self.assertEqual(inspect(task,calls)['final']['trace_support'],'unknown')

    def test_wrong_target_unconfirmed_write_or_failed_deletion_is_not_support(self):
        for mode in ('target','write','deletion'):
            with self.subTest(mode=mode):
                task,calls=fixture()
                if mode=='target':calls[7][1]['file_path']='~/elsewhere.csv'
                elif mode=='write':calls[7][2]['message']='Failed.'
                else:calls[8][2]['message']='Failed.'
                self.assertEqual(inspect(task,calls)['final']['trace_support'],'unknown')

    def test_later_unhandled_write_or_unknown_effect_invalidates_earlier_support(self):
        task,calls=fixture();calls.append(('file_system__delete_file',{'access_token':'synthetic-file','file_path':'~/backups/spotify.csv'},{}))
        self.assertEqual(inspect(task,calls)['final']['trace_support'],'unknown')
        task,calls=fixture();s,e,u=records(calls);e[-1]['effects_unknown']=True
        self.assertEqual(inspect_export(task,s,e,u)['final']['trace_support'],'unknown')

    def test_no_future_metadata_can_validate_a_backup_before_deletion(self):
        task,calls=fixture();detail=calls.pop(6);calls.insert(8,detail)
        r=inspect(task,calls);self.assertEqual(r['final']['source_metadata_ids'],2)
        self.assertEqual(r['final']['trace_support'],'unknown')
        self.assertFalse(r['final']['supported_backup_preceded_deletion'])

    def test_unhandled_later_effect_does_not_leave_a_stale_contradiction(self):
        task,calls=fixture();calls[7][1]['content']='Title,Artists\nOne,A\n'
        calls.append(('file_system__update_file',{'access_token':'synthetic-file','file_path':'~/backups/spotify.csv',
            'content':'Title,Artists\nOne,A\nTwo,B|C\n'},{}))
        r=inspect(task,calls);self.assertEqual(r['final']['trace_support'],'unknown')
        self.assertEqual(r['boundaries'][7]['trace_support'],'contradicted')

    def test_task_scope_and_chronology_are_not_reinterpreted(self):
        task,calls=fixture();s,e,u=records(calls)
        with self.assertRaises(ValueError):inspect_export({**task,'ground_truth_loaded':True},s,e,u)
        with self.assertRaises(ValueError):inspect_export({**task,'instruction':task['instruction']+' Email it.'},s,e,u)
        with self.assertRaises(ValueError):inspect_export(task,s,e[::-1],u)
        self.assertEqual(task,TASK)


if __name__=='__main__':unittest.main()
