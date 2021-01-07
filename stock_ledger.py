"""
stock_ledger.py - a small library for analyzing export CSVs from equity accounts
"""

import pandas as pd
import numpy as np
import os

class StockLedger:

    @staticmethod
    def from_trp( export_file ):
        """Create a StockLedger from a T Rowe Price workplace retirement export.

        Downloading these files is a PITA, but the transactions sent
        to Mint/Tiller are not very reliable, so you'll need them.

        Go to your account, then account activity. You can only
        download one year of data at a time. Check all options shown,
        select 1/1 to 12/31 for your first year, then click
        submit. Then click export to csv. Repeat for N years.

        On the bright side, you only need to download the historical
        files once. In any case, it may pay to implement a scraper.

        Parameters
        ----------
        export_file : str or file object
            Export CSV to load, or a directory containing such CSVs.
        """

        # Get a list of all CSVs
        csv_files = []
        if os.path.isdir( export_file ):
            for fname in os.listdir( export_file ):
                if fname[-3:].lower() == "csv":
                    csv_files.append( os.path.join( export_file, fname ) )
        else:
            csv_files.append( export_file )

        # Load the dataframes
        dfs = []
        for fname in csv_files:
            # Skip the first 2 rows -- just describes the date range used
            df = pd.read_csv( fname, skiprows=2, usecols=["Date","Amount","Shares","Price","Amount","Source","Activity Type","Investment"] )

            # Replace Date with a proper date index
            df[ "date" ] = pd.to_datetime( df[ "Date" ] )
            df.drop( "Date", axis="columns", inplace=True )

            # convert amount and share price to simple floats
            df[ "amount" ] = df.Amount.replace( "[\$,]", "", regex=True ).astype( float )
            df[ "share_price" ] = df.Price.replace( "[\$,]", "", regex=True ).astype( float )
            df.drop( [ "Amount", "Price" ], axis="columns", inplace=True )

            # Convert shares to float
            df[ "shares" ] = df.Shares.astype( float )
            df.drop( "Shares", axis="columns", inplace=True )

            # Rename redemption fee to just fee
            df.loc[ df[ "Activity Type" ].str.strip() == "Redemption Fee", "Activity Type" ] = "Fee"

            # Invert the signs where appropriate
            for transaction_type in [ "Exchange Out", "Fee" ]:
                for colname in [ "amount", "shares" ]:
                    df.loc[ df[ "Activity Type" ].str.strip() == transaction_type, colname ] = -df[ colname ]

            # Cleanup the last three columns
            df.rename( { "Activity Type": "type",
                         "Investment": "fund",
                         "Source": "source" }, axis=1, inplace=True )
            df.type = df.type.str.strip()
            df.fund = df.fund.str.strip()
            df.source = df.source.str.strip()

            # Rename both "Exchange In" and "Exchange Out" to just exchange
            df.loc[ df.type == "Exchange In", "type" ] = "Exchange"
            df.loc[ df.type == "Exchange Out", "type" ] = "Exchange"

            # Add it to the list
            dfs.append( df )

        # Merge the dataframes & wrap the result
        return StockLedger( pd.concat( dfs, axis='rows', ignore_index=True ) )

    def __init__( self, df ):
        """Don't use this, use TransactionLedger.from_mint() or TransactionLedger.from_tiller()"""
        self.df = df

    def __repr__( self ):
        """print the inner DF"""
        return str( self.df )

    def __getattr__( self, attr ):
        """Forward all unknown APIs to the wrapped dataframe."""
        if hasattr( self.df, attr ):
            return getattr( self.df, attr )
        raise AttributeError( "'{}' is not a known attribute of either {} or {}".format( attr, self.__class__.__name__, self.df.__class__.__name__ ) )

    def in_funds( self, fund_or_funds, invert=False ):
        """Filter by fund.

        Remove all transactions in funds other than those
        specified.

        Parameters
        ----------
        fund_or_funds : str or collection( str )
            The funds to filter against
        invert : bool
            Whether to invert the match

        Returns
        -------
        ret : StockLedger
            The filtered transactions

        """
        if isinstance( fund_or_funds, str ):
            fund_or_funds = [ fund_or_funds ]
        msk = self.df.fund.isin( fund_or_funds )
        if invert:
            msk = ~msk
        return StockLedger( self.df[ msk ].copy() )

    def contributions( self ):
        """Filter for contributions.

        Remove all non-contribution transactions.

        Returns
        -------
        ret : StockLedger
            The filtered transactions
        """
        return StockLedger( self.df[ self.df.type == "Contribution" ].copy() )

    def fees( self ):
        """Filter for fees.

        Remove all non-fee transactions.

        Returns
        -------
        ret : StockLedger
            The filtered transactions
        """
        return StockLedger( self.df[ self.df.type == "Fee" ].copy() )

    def dividends( self ):
        """Filter for dividends.

        Remove all non-dividend transactions.

        Returns
        -------
        ret : StockLedger
            The filtered transactions
        """
        return StockLedger( self.df[ self.df.type == "Dividend" ].copy() )

    def exchanges( self ):
        """Filter for exchanges.

        Remove all non-exchange transactions.

        Returns
        -------
        ret : StockLedger
            The filtered transactions
        """
        return StockLedger( self.df[ self.df.type == "Exchange" ].copy() )

    def portfolio( self ):
        """Get the final portfolio.

        Get the final number of shares in each fund.

        Returns
        -------
        portfolio : pd.Series of float
            The number of shares per fund.
        """
        ret = self.df.groupby( "fund" ).shares.sum().round( 2 )
        return ret[ ret.abs() > 0 ]
