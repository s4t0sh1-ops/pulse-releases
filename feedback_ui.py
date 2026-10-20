"""Track-level negative feedback, with the same colours and gentle motion as Android."""
import json
from PySide6.QtCore import Qt
from matching import recording_key

class FeedbackUI:
    def __init__(self):
        self.bad_accounts={};self.bad_owner=None;self.bad_tracks={}
        try:self.bad_accounts=json.loads((self.data_dir/'dislikes.json').read_text(encoding='utf8'))
        except (OSError,ValueError):pass
        super().__init__()
        self.current_dislike=self.icon_button('dislike','Не нравится — реже рекомендовать эту песню',self.dislike_current);self.current_dislike.setCheckable(True)
        buttons=self.transport.layout();buttons.insertWidget(0,self.current_favorite);buttons.addWidget(self.current_dislike)
        self.now_page.dislike=self.icon_button('dislike','Не нравится',self.dislike_current);self.now_page.dislike.setCheckable(True)
        controls=self.now_page.like.parentWidget().layout()
        # The full-card controls are a nested horizontal layout; locate by the like button.
        def find(layout):
            for i in range(layout.count()):
                item=layout.itemAt(i)
                if item.widget() is self.now_page.like:return layout
                if item.layout():
                    found=find(item.layout())
                    if found:return found
            return None
        line=find(controls)
        if line:line.insertWidget(line.count()-1,self.now_page.dislike)
        self.media.positionChanged.connect(lambda _:self.refresh_feedback())
        self.refresh_feedback()

    def feedback_account(self):
        p=self.profile;owner=(p.get('provider','local')+':'+str(p.get('provider_id') or p.get('id'))) if p else ''
        if owner!=self.bad_owner:
            if self.bad_owner is not None:self.bad_accounts[self.bad_owner]=self.bad_tracks
            self.bad_owner=owner;self.bad_tracks=dict(self.bad_accounts.get(owner,{}))

    def disliked(self,row):
        self.feedback_account();return str(row['id']) in self.bad_tracks or recording_key(row) in {recording_key(r) for r in self.bad_tracks.values()}

    def save_feedback(self):
        self.bad_accounts[self.bad_owner]=self.bad_tracks;self.save_data('dislikes.json',self.bad_accounts)

    def dislike_current(self):
        if not 0<=self.current<len(self.queue):return
        row=self.queue[self.current];bad=self.disliked(row)
        if bad:self.bad_tracks={k:r for k,r in self.bad_tracks.items() if recording_key(r)!=recording_key(row) and k!=str(row['id'])}
        else:
            self.bad_tracks[str(row['id'])]=dict(row)
            self.favorites={k:r for k,r in self.favorites.items() if recording_key(r)!=recording_key(row) and k!=str(row['id'])}
            self.save_data('favorites.json',self.favorites)
            self.home_rows=[r for r in self.home_rows if not self.disliked(r)]
        self.save_feedback();self.reco_signature=None;self.refresh_feedback()
        if self.view=='home':self.render(self.home_rows)

    def refresh_feedback(self):
        if not hasattr(self,'current_dislike'):return
        row=self.queue[self.current] if 0<=self.current<len(self.queue) else None
        liked=bool(row and row['id'] in self.favorites);bad=bool(row and self.disliked(row))
        for button in (self.current_favorite,self.now_page.like):button.setChecked(liked)
        for button in (self.current_dislike,self.now_page.dislike):button.setChecked(bad)

    def favorite_current(self):
        super().favorite_current();self.clear_liked_dislikes();self.refresh_feedback()

    def favorite(self,index):
        super().favorite(index);self.clear_liked_dislikes();self.refresh_feedback()

    def clear_liked_dislikes(self):
        self.feedback_account();liked={recording_key(r) for r in self.favorites.values()}
        self.bad_tracks={k:r for k,r in self.bad_tracks.items() if recording_key(r) not in liked};self.save_feedback()

    def prepare_wave_rows(self,rows,context=None,queued=None):
        return super().prepare_wave_rows([r for r in rows if not self.disliked(r)],context,queued)

    def render(self,rows):
        if self.view in ('home','wave'):rows=[r for r in rows if not self.disliked(r)]
        super().render(rows)

    def play_index(self,index):
        # Do not put a previously rejected track back into an automatically extended wave.
        if getattr(self,'wave_mode',False):
            while 0<=index<len(self.queue) and self.disliked(self.queue[index]):index+=1
        super().play_index(index);self.refresh_feedback()
